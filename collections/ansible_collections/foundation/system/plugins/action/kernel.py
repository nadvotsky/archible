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
        variables = self._process_vars(self._task.vars)

        seed, seed_hash = self._read_current_cmdline(task_vars)
        patch, patch_hash = self._construct_patch(seed, variables)
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

    def _process_vars(self, raw_vars: dict) -> tuple[Arguments, Cmdline]:
        if not isinstance(raw_vars, dict):
            raise AnsibleActionFail("Invalid module variables, expected a mapping")
        elif len(raw_vars) == 0:
            raise AnsibleActionFail("No-op module invocation")

        def is_value_wrong(value):
            return value is False or not isinstance(value, (str, bool))

        def finalize_value(value) -> None | str:
            return None if value is True else str(value)

        args: Cmdline = {}
        for key, value in raw_vars.items():
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

            if val and len((vector := val.split(","))) > 1:
                cmdline[key] = list(filter(None, vector))
                if len(cmdline[key]) == 0:
                    self._display.warning("Empty list in '{}'.".format(val))

                continue

            cmdline[key] = val

        return cmdline, hashlib.md5(content.encode()).digest()

    def _construct_patch(self, seed: Cmdline, variables: Cmdline) -> tuple[str, bytes]:
        def format_line(key: str, value: None | str | typing.Sequence[str]) -> str:
            if value is None:
                return key
            elif isinstance(value, str):
                return f"{key}={value}"

            return "{}={}".format(key, ",".join(tuple(dict.fromkeys(value).keys())))

        def prettify_type(t: typing.Type):
            return {str: "option", list: "list"}.get(t, "flag")

        lines = []
        for key in seed.keys():
            if key not in variables:
                lines.append(format_line(key, seed[key]))
                continue

            new_value = variables[key]
            was_type, new_type = type(seed[key]), type(new_value)
            if was_type is new_type:
                if isinstance(new_value, list):
                    lines.append(format_line(key, (*seed[key], *new_value)))
                else:
                    lines.append(format_line(key, new_value))
            elif was_type is not str and new_type is not list:
                raise AnsibleActionFail(
                    "'{}' type mismatch: expected {}, got {}.".format(
                        key,
                        prettify_type(was_type),
                        prettify_type(new_type),
                    )
                )
            else:
                lines.append(format_line(key, (seed[key], *new_value)))

        for key in filter(lambda k: k not in seed, variables.keys()):
            lines.append(format_line(key, variables[key]))

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
