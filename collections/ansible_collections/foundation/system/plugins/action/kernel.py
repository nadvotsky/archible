#
# foundation.system.kernel - manage kernel command-line with initramfs regeneration.
#
# Follow the project README for more information.
#

import typing

import base64
import hashlib

from ansible.errors import AnsibleActionFail
from ansible.plugins.action import ActionBase
from ansible.constants import COLOR_CHANGED

from ansible_collections.foundation.util.dispatch import ansible_dispatch
from ansible_collections.foundation.util.types import RawResult, TaskVars


class Arguments(typing.TypedDict):
    headless: bool


type Cmdline = typing.Mapping[str, None | str | list[str]]


class ActionModule(ActionBase):
    _CMDLINE_FILE = "/etc/kernel/cmdline"

    def run(self, tmp: None = None, task_vars: dict = None) -> RawResult:
        result = RawResult()

        spec = dict(headless=dict(type="bool", required=True))
        args: Arguments = self.validate_argument_spec(spec)[1]
        env = self._process_env(self._task.environment.pop())

        seed, seed_hash = self._read_current_cmdline(task_vars)
        patch, patch_hash = self._construct_patch(seed, env)
        if self._task.check_mode or seed_hash == patch_hash:
            return result

        for task_name, task_fn in {
            "commit": lambda: self._commit_changes(task_vars, patch),
            "kernel-install": lambda: self._kernel_install(args["headless"], task_vars),
        }.items():
            context, local_result = task_fn()
            if local_result.get("failed") is True:
                return local_result

            self._display.display(f"changed: ({task_name}) => '{context}'", COLOR_CHANGED)

        return RawResult(changed=True)

    def _process_env(self, raw_env: dict) -> tuple[Arguments, Cmdline]:
        if not isinstance(raw_env, dict):
            raise AnsibleActionFail("Invalid module environment, expected a mapping")
        elif len(raw_env) == 0:
            raise AnsibleActionFail("No-op module invocation")

        def is_value_wrong(value):
            return value is False or not isinstance(value, (str, bool))

        def finalize_value(value) -> None | str:
            return None if value is True else str(value)

        args: Cmdline = {}
        for key, value in raw_env.items():
            vector = value if isinstance(value, list) else [value]
            if len(vector) == 0 or any(map(is_value_wrong, vector)):
                raise AnsibleActionFail(f"'{key}' must only allows primitives")

            if isinstance(value, list):
                args[key] = list(map(finalize_value, value))
            else:
                args[key] = finalize_value(value)

        return args

    def _read_current_cmdline(self, task_vars: TaskVars) -> tuple[Cmdline, bytes]:
        result = self._execute_module(
            module_name="ansible.builtin.slurp",
            module_args=dict(src=self._CMDLINE_FILE),
            task_vars=task_vars,
        )
        if result.get("failed"):
            return {}, b""

        cmdline, content = {}, base64.b64decode(result["content"].encode()).decode()
        for line in content.split():
            key, _, val = line.partition("=")
            if any(filter(lambda v: v == "", (key, val))):
                raise AnsibleActionFail("Empty component ({}={}).".format(key, val))
            #
            # Comma-separated values are naturally treated as list in many kernel modules.
            #
            if val and len((vector := val.split(","))) > 1:
                cmdline[key] = list(filter(None, vector))
                if len(cmdline[key]) == 0:
                    self._display.warning("Empty list in '{}'.".format(val))

                continue

            #
            # Exclusive list of parameters that may be specified multiple times.
            #
            if key in ('video'):
                cmdline[key] = cmdline.get("key", "") + " " + val
                continue

            #
            # None denotes boolean flags.
            #
            cmdline[key] = None if val == "" else val

        return cmdline, hashlib.md5(content.encode()).digest()

    def _construct_patch(self, seed: Cmdline, env: Cmdline) -> tuple[str, bytes]:
        def format_line(key: str, value: None | str | typing.Sequence[str]) -> str:
            if value is None:
                #
                # Boolean flag, rendered as is.
                #
                return key
            elif isinstance(value, str):
                #
                # Option with value, separated with equals symbol.
                #
                return f"{key}={value}"

            #
            # Comma-separated list.
            #
            return "{}={}".format(key, ",".join(tuple(dict.fromkeys(value).keys())))

        def prettify_type(t: typing.Type):
            return {str: "option", list: "list"}.get(t, "flag")

        lines = []
        #
        # Handle existing flags.
        #
        for key in seed.keys():
            if key not in env:
                lines.append(format_line(key, seed[key]))
                continue

            new_value = env[key]
            was_type, new_type = type(seed[key]), type(new_value)
            if was_type is new_type:
                #
                # Merge lists.
                #
                if isinstance(new_value, list):
                    lines.append(format_line(key, (*seed[key], *new_value)))
                else:
                    lines.append(format_line(key, new_value))
            #
            # Allow upgrading option to list.
            #
            elif isinstance(was_type, str) and isinstance(new_type, list):
                lines.append(format_line(key, (seed[key], *new_value)))
            else:
                raise AnsibleActionFail(
                    "'{}' type mismatch: expected {}, got {}.".format(
                        key,
                        prettify_type(was_type),
                        prettify_type(new_type),
                    )
                )

        #
        # Append new flags.
        #
        for key in filter(lambda k: k not in seed, env.keys()):
            lines.append(format_line(key, env[key]))

        return (ret := " ".join(lines) + "\n"), hashlib.md5(ret.encode()).digest()

    def _commit_changes(self, task_vars: TaskVars, patch: str) -> tuple[str, RawResult]:
        result = ansible_dispatch(
            self,
            "ansible.builtin.copy",
            dict(dest=self._CMDLINE_FILE, content=patch),
            task_vars,
        )

        return self._CMDLINE_FILE, result

    def _kernel_install(self, headless: bool, task_vars: TaskVars) -> tuple[str, RawResult]:
        info_string = []

        #
        # Non-universal booster builds target the current system and loaded modules. In headless setups, this may
        #  include unwanted modules and/or exclude critical ones (e.g., nvme).
        #
        # Once the system is actually booted, any system update will regenerate the optimized initramfs, as expected.
        #
        if headless is True:
            self._task.environment.append(dict(KERNEL_INSTALL_BOOSTER_UNIVERSAL=1))
            info_string.append("KERNEL_INSTALL_BOOSTER_UNIVERSAL=1")

        result = ansible_dispatch(
            self,
            "ansible.builtin.command",
            dict(argv=["/usr/bin/kernel-install", "add-all"]),
            task_vars=task_vars,
        )
        if result.get("failed") is True:
            return "", result
        else:
            info_string.append(result.get("stdout"))

        return ": ".join(info_string), result
