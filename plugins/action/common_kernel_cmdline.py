import typing
import itertools
import base64

from ansible.errors import AnsibleActionFail
from ansible.plugins.action import ActionBase
from ansible.playbook.task import Task

from ansible.constants import COLOR_CHANGED, COLOR_ERROR

from ansible.plugins.loader import action_loader


class Result(typing.TypedDict):
    changed: typing.NotRequired[bool]
    failed: typing.NotRequired[bool]


type Cmdline = typing.Mapping[str, None | str | list[str]]


class ActionModule(ActionBase):
    _CMDLINE_FILE = "/etc/kernel/cmdline"

    def run(self, tmp: None = None, task_vars: dict = None) -> Result:
        self._display.warning(f"{self._connection.become=}")
        args, result = self._process_args(), Result()
        if self._task.check_mode is True:
            return result

        seed, seed_hash = self._read_current_cmdline(task_vars)
        patch = self._construct_patch(seed, args)
        if seed_hash == hash(patch):
            return result

        for task_name, task_fn in {
            "commit": lambda: self._commit_changes(task_vars, patch),
            "kernel-install": lambda: self._kernel_install(task_vars),
        }.items():
            context, local_result = task_fn()
            if local_result.get("failed") is True:
                self._display.display(f"failed: ({task_name})", COLOR_ERROR)
                return local_result

            self._display.display(
                f"changed: ({task_name}) => '{context}'", COLOR_CHANGED
            )

        return Result(changed=True)

    def _process_args(self) -> Cmdline:
        def is_value_wrong(value):
            return value is False or not isinstance(value, (bool, int, str))

        def finalize_value(value) -> None | str:
            return None if value is True else str(value)

        if not isinstance(self._task.args, dict):
            raise AnsibleActionFail("Invalid module arguments, expected a mapping.")
        elif len(self._task.args) == 0:
            raise AnsibleActionFail("No-op module invocation.")

        args: Cmdline = {}
        for key, value in self._task.args.items():
            if isinstance(value, list):
                if len(value) == 0 or any(map(is_value_wrong, value)):
                    raise AnsibleActionFail(f"'{key}' must be a list of primitives.")
                args[key] = list(map(finalize_value, value))
            else:
                if is_value_wrong(value):
                    raise AnsibleActionFail(f"'{key}' must be a primitive.")
                args[key] = finalize_value(value)

        return args

    def _read_current_cmdline(self, task_vars: dict) -> tuple[Cmdline, int]:
        result = self._execute_module(
            module_name="ansible.builtin.slurp",
            module_args=dict(src=self._CMDLINE_FILE),
            task_vars=task_vars,
        )
        if result.get("failed"):
            return {}, hash("")

        cmdline, content = {}, base64.b64decode(result["content"].encode()).decode()
        for line in content.split():
            key, val, *_ = itertools.chain(line.split("=", 1), [None])
            if any(filter(lambda v: v == "", (key, val))):
                raise AnsibleActionFail("Empty component ({}={}).".format(key, val))

            if val is not None and len((vals := val.split(","))) > 1:
                cmdline[key] = list(filter(None, vals))
                if len(cmdline[key]) == 0:
                    self._display.warning("Empty comma values in '{}'.".format(val))

                continue

            cmdline[key] = val

        return cmdline, hash(content)

    def _construct_patch(self, seed: Cmdline, args: Cmdline) -> str:
        def format_line(key: str, value: None | str | typing.Sequence[str]) -> str:
            if value is None:
                return key
            elif isinstance(value, str):
                return f"{key}={value}"

            return "{}={}".format(key, ",".join(tuple(dict.fromkeys(value).keys())))

        def prettify_type(t):
            return {str: "option", list: "list"}.get(t, "flag")

        lines = []
        for key in seed.keys():
            if key not in args:
                lines.append(format_line(key, seed[key]))
                continue

            new_value = args[key]
            new_type = type(new_value)
            was_type = type(seed[key])
            if was_type == new_type:
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

        for key in filter(lambda k: k not in seed, args.keys()):
            lines.append(format_line(key, args[key]))

        return " ".join(lines) + "\n"

    def _commit_changes(self, task_vars: dict, patch: str) -> tuple[str, Result]:
        action = action_loader.get(
            "ansible.builtin.copy",
            task=Task.load(
                {
                    "ansible.builtin.copy": {
                        "dest": self._CMDLINE_FILE,
                        "content": patch,
                    }
                },
                block=self._task,
                loader=self._loader,
                variable_manager=self._task.get_variable_manager(),
            ),
            connection=self._connection,
            play_context=self._play_context,
            loader=self._loader,
            templar=self._templar,
            shared_loader_obj=self._shared_loader_obj,
        )
        return self._CMDLINE_FILE, action.run(task_vars=task_vars)

    def _kernel_install(self, task_vars: dict) -> Result:
        info_string = []
        if self._templar.template(task_vars["policy"]["headless"]) is True:
            self._task.environment.append(dict(KERNEL_INSTALL_BOOSTER_UNIVERSAL=1))
            info_string.append("KERNEL_INSTALL_BOOSTER_UNIVERSAL=1")

        result = self._execute_module(
            module_name="ansible.builtin.command",
            module_args=dict(argv=["/usr/bin/kernel-install", "add-all"]),
            task_vars=task_vars,
        )
        if result.get("failed") is True:
            return "", result
        else:
            info_string.append(result.get("stdout"))

        return ": ".join(info_string), result
