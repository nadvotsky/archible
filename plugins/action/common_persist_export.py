import typing
import shlex
import dataclasses
import itertools
import os.path
import pathlib

from ansible.errors import AnsibleActionFail
from ansible.plugins.action import ActionBase
from ansible.constants import COLOR_CHANGED, COLOR_OK, COLOR_ERROR


@dataclasses.dataclass(kw_only=True)
class Target:
    key: str
    dir: str | None = None


@dataclasses.dataclass(kw_only=True)
class Shell(Target):
    shell: str


Archive = Target


@dataclasses.dataclass(kw_only=True)
class Arguments:
    dir: str | None = None
    shells: list[Shell]
    archives: list[Archive]


class Result(typing.TypedDict):
    failed: typing.NotRequired[bool]
    msg: typing.NotRequired[str]
    changed: typing.NotRequired[bool]


class ActionModule(ActionBase):
    def run(self, tmp: None = None, task_vars: dict = None) -> Result:
        args = self._validate_args()

        persist = self._templar.template(
            self._templar.template(task_vars["policy"]["persist"])
        )
        for target, command, stdin in self._yield_commands(persist, args):
            if self._task.check_mode is True:
                self._display.display(
                    "ok: ({}) => ({}, {})".format(target.key, target.dir, command),
                    COLOR_OK,
                )
                continue

            rc, _, stderr = self._binary_command(command, target.dir, stdin)
            if rc != 0:
                self._display.display("failed: ({})".format(target.key), COLOR_ERROR)
                raise AnsibleActionFail(
                    message="Non-zero return code.",
                    result=dict(rc=rc, dir=target.dir, command=command, stderr=stderr),
                )

            self._display.display("changed: ({})".format(target.key), COLOR_CHANGED)

        return Result(changed=True)

    def _validate_args(self) -> Arguments:
        _, raw_args = self.validate_argument_spec(argument_spec=self._build_spec())
        if all(
            (
                raw_args[collection] is None or len(raw_args[collection]) == 0
                for collection in ("shells", "archives")
            )
        ):
            raise AnsibleActionFail("No-op action.")

        base = raw_args["dir"]
        if base is not None and not os.path.isabs(base):
            raise AnsibleActionFail(
                "Base directory '{}' must be absolute.".format(base)
            )

        args = Arguments(dir=base, archives=[], shells=[])
        for raw_items, dest, target_class in (
            (raw_args["shells"], args.shells, Shell),
            (raw_args["archives"], args.archives, Target),
        ):
            dest.extend(
                (
                    target_class(**self._validate_target_dict(base, dictionary))
                    for dictionary in raw_items
                )
            )

        return args

    def _build_spec(self) -> dict:
        any_target = dict(
            key=dict(type="str", required=True),
            dir=dict(type="str", required=False),
        )
        any_target_collection = dict(type="list", required=False, elements="dict")

        return {
            "dir": dict(type="path", required=False),
            "shells": {
                **any_target_collection,
                "options": {
                    **any_target,
                    "shell": dict(type="str", required=True),
                },
            },
            "archives": {
                **any_target_collection,
                "options": any_target,
            },
        }

    def _validate_target_dict(self, base: str | None, target: dict) -> dict:
        key = pathlib.Path(target["key"])
        if key.is_absolute() or len(key.parts) != 2:
            raise AnsibleActionFail(
                "Expected key to have exactly two components, got '{}'.".format(
                    target["key"]
                )
            )

        directory = target["dir"]
        match base, directory:
            case _, str(d) if os.path.isabs(d):
                pass
            case None, _:
                raise AnsibleActionFail(
                    "Relative dir '{}' requires base dir.".format(directory)
                )
            case _, None:
                target["dir"] = base
            case _:
                target["dir"] = os.path.join(base, directory)

        return target

    TAR_COMMAND = (
        "/usr/bin/tar",
        "--extract",
        "--no-same-owner",
        "--preserve-permissions",
        "--zstd",
        "--file",
        "-",
    )

    def _yield_commands(
        self, persist: str, args: Arguments
    ) -> tuple[Target, str, bytes]:
        for target in itertools.chain(args.shells, args.archives):
            content_path = pathlib.Path(persist, target.key)
            if not content_path.is_file():
                raise AnsibleActionFail(
                    message="Persist item '{}' does not exist.".format(target.key),
                    result=dict(persist=persist),
                )

            if isinstance(target, Shell):
                command = target.shell
            elif isinstance(target, Archive):
                command = " ".join(self.TAR_COMMAND)

            yield target, command, content_path.read_bytes()

    def _binary_command(
        self, command: str, directory: str, stdin: bytes
    ) -> tuple[int, bytes, bytes]:
        command = self._connection._shell.append_command(
            "cd {}".format(shlex.quote(directory)),
            command,
        )

        remote, become = self._get_remote_user(), self.get_become_option("become_user")
        if self._connection.become and (become != remote or not any((become, remote))):
            command = self._connection.become.build_become_command(
                command,
                self._connection._shell,
            )

        if self._connection.allow_executable:
            command = self._connection._shell.append_command(command, "sleep 0")
            if executable := self._play_context.executable:
                command = executable + " -c " + shlex.quote(command)

        return self._connection.exec_command(command, in_data=stdin, sudoable=True)
