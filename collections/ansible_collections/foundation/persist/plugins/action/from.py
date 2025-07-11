import typing

import dataclasses
import itertools
import os.path
import pathlib

from ansible.errors import AnsibleActionFail
from ansible.plugins.action import ActionBase
from ansible.constants import COLOR_CHANGED, COLOR_OK

from ansible_collections.foundation.util.types import RawResult, TaskVars
from ansible_collections.foundation.util.dispatch import (
    ansible_binary_command,
)
from ansible_collections.foundation.util.specs import validate_spec


@dataclasses.dataclass
class Defaults:
    base: str | None
    persist: str


@dataclasses.dataclass
class Target:
    key: str
    dir: str | None


@dataclasses.dataclass
class Archive(Target):
    perms: tuple[str, str]


@dataclasses.dataclass
class Shell(Target):
    cmd: str


@dataclasses.dataclass
class Inputs:
    defaults: Defaults
    shells: list[Shell]
    archives: list[Archive]


class ActionModule(ActionBase):
    TAR_COMMAND = (
        "/usr/bin/tar",
        "--extract",
        "--no-same-owner",
        "--preserve-permissions",
        "--owner={owner}",
        "--group={group}",
        "--gzip",
        "--file",
        "-",
    )

    def run(self, tmp: None = None, task_vars: TaskVars = None) -> RawResult:
        inputs = self._validate_inputs()
        if self._premature_skipped(inputs):
            return RawResult(skipped=True)

        result = RawResult()
        for target, command, stdin in self._yield_commands(inputs):
            context = "({}:{}) => ({}, {})".format(type(target).__name__.lower(), target.key, target.dir, command)
            if self._task.check_mode is True:
                self._display.display(f"ok: {context}", COLOR_OK)
                continue

            rc, _, stderr = ansible_binary_command(self, command, target.dir, stdin)
            if rc != 0:
                raise AnsibleActionFail(
                    message="Non-zero return code",
                    result=dict(rc=rc, dir=target.dir, command=command, stderr=stderr),
                )

            result["changed"] = True
            self._display.display(f"changed: {context}", COLOR_CHANGED)

        return result

    def _validate_inputs(self) -> Inputs:
        specs = self._build_spec()
        _, raw_args = self.validate_argument_spec(dict(specs.pop("defaults")["options"]))
        if raw_args["base"] is not None and not os.path.isabs(raw_args["base"]):
            raise AnsibleActionFail("Base directory '{}' must be absolute".format(raw_args["base"]))
        if not os.path.isdir(raw_args["persist"]):
            raise AnsibleActionFail("Persist directory '{}' must exist".format(raw_args["persist"]))

        raw_vars = validate_spec(specs, self._templar.template(self._task.vars))
        if all(
            (raw_vars[collection] is None or len(raw_vars[collection]) == 0 for collection in ("shells", "archives"))
        ):
            raise AnsibleActionFail("No-op action")

        inputs = Inputs(defaults=Defaults(**raw_args), archives=[], shells=[])
        for raw_items, dest, target_class in (
            (raw_vars["shells"], inputs.shells, Shell),
            (raw_vars["archives"], inputs.archives, Archive),
        ):
            dest.extend(
                (target_class(**self._validate_target_dict(inputs.defaults, dictionary)) for dictionary in raw_items)
            )

        return inputs

    @staticmethod
    def _build_spec() -> dict:
        target_spec = dict(
            key=dict(type="str", required=True),
            dir=dict(type="str", required=False),
        )
        target_collection_spec = dict(type="list", required=False, elements="dict")

        return {
            "defaults": {
                "type": "dict",
                "required": True,
                "options": {
                    "base": dict(type="path", required=False),
                    "persist": dict(type="path", required=True),
                },
            },
            "shells": {
                **target_collection_spec,
                "options": {
                    **target_spec,
                    "cmd": dict(type="str", required=True),
                },
            },
            "archives": {
                **target_collection_spec,
                "options": {
                    **target_spec,
                    "perms": dict(type="str", required=True),
                },
            },
        }

    @staticmethod
    def _validate_target_dict(defaults: Defaults, target: dict) -> dict:
        key = pathlib.Path(target["key"])
        if key.is_absolute() or len(key.parts) != 2:
            raise AnsibleActionFail("Expected key to have exactly two components, got '{}'".format(target["key"]))

        directory = target["dir"]
        match defaults.base, directory:
            case _, str(d) if os.path.isabs(d):
                pass
            case _, str(d) if not d.startswith("./"):
                raise AnsibleActionFail("Relative dir '{}' requires './' prefix".format(d))
            case None, _:
                raise AnsibleActionFail("Relative dir '{}' requires base dir".format(directory))
            case _, None:
                target["dir"] = defaults.base
            case _:
                target["dir"] = os.path.normpath(os.path.join(defaults.base, directory))

        if "perms" in target:
            target["perms"] = target["perms"].split(":", maxsplit=2)
            if len(target["perms"]) != 2:
                raise AnsibleActionFail("Permissions must be given as 'owner:group', not {}".format(target["perms"]))

        return target

    @staticmethod
    def _premature_skipped(inputs: Inputs) -> bool:
        return any(
            [
                not os.path.isfile(os.path.join(inputs.defaults.persist, target.key))
                for target in itertools.chain(inputs.shells, inputs.archives)
            ]
        )

    def _yield_commands(self, inputs: Inputs) -> typing.Generator[tuple[Target, str, bytes]]:
        for target in itertools.chain(inputs.shells, inputs.archives):
            content_path = pathlib.Path(inputs.defaults.persist, target.key)

            if isinstance(target, Shell):
                command = target.cmd
            elif isinstance(target, Archive):
                command = " ".join(self.TAR_COMMAND).format(owner=target.perms[0], group=target.perms[1])
            else:
                raise AnsibleActionFail(f"Unreachable target {target}")

            yield target, command, content_path.read_bytes()
