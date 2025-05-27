import os.path
import dataclasses
import typing
import functools
import re

from ansible.template import Templar
from ansible.plugins.action import ActionBase
from ansible.errors import AnsibleActionFail
from ansible.constants import COLOR_CHANGED, COLOR_OK, COLOR_ERROR


@dataclasses.dataclass
class Arguments:
    wipe: list[str] = dataclasses.field(default_factory=list)
    install: list[str] = dataclasses.field(default_factory=list)


class Result(typing.TypedDict):
    changed: typing.NotRequired[bool]
    failed: typing.NotRequired[bool]
    msg: typing.NotRequired[str]


class TaskVars:
    def __init__(self, templar: Templar, raw: dict[str, typing.Any]):
        self.templar = templar
        self.raw = raw

    def __getitem__(self, key: str) -> str:
        first, *rest = key.split(".")
        try:
            return self.templar.template(
                functools.reduce(lambda acc, val: acc[val], rest, self.raw[first])
            )
        except KeyError:
            raise AnsibleActionFail("Undefined key '{}'.".format(key))


class Task(typing.Protocol):
    def info(self) -> tuple[str, str]: ...
    def execution_context(self) -> tuple[str, dict[str, typing.Any]]: ...
    def execution_wrap(self, result: Result) -> Result | None: ...


class UninstallTask(Task):
    def __init__(self, task_vars: TaskVars, tool: str):
        self.cmdline = ("/usr/bin/mise", "uninstall", "--yes", "--all", tool)

    def info(self) -> tuple[str, str]:
        return "uninstall", " ".join(self.cmdline)

    def execution_context(self) -> tuple[str, dict[str, typing.Any]]:
        return "ansible.builtin.command", dict(argv=self.cmdline)

    def execution_wrap(self, result: Result) -> Result | None:
        if result.get("failed") is True:
            return None

        return result


class WipeTask(Task):
    TOOL_NAME_REGEX = re.compile(r"[:\/]")

    def __init__(self, task_vars: TaskVars, tool: str):
        policy = task_vars["users.user.layout"]
        share = task_vars["dev.mise.share"]
        self.path = os.path.join(
            share.get(policy) or share["default"],
            "installs",
            self.TOOL_NAME_REGEX.sub("-", tool),
        )

    def info(self) -> tuple[str, str]:
        return "wipe", self.path

    def execution_context(self) -> tuple[str, dict[str, typing.Any]]:
        return "ansible.builtin.file", dict(path=self.path, state="absent")

    def execution_wrap(self, result: Result) -> Result | None:
        return result


class InstallTask(Task):
    def __init__(self, task_vars: TaskVars, tool: str):
        self.cmdline = ["/usr/bin/mise", "install", tool]

    def info(self) -> tuple[str, str]:
        return "install", " ".join(self.cmdline)

    def execution_context(self) -> tuple[str, dict[str, typing.Any]]:
        return "ansible.builtin.command", dict(argv=self.cmdline)

    def execution_wrap(self, result: Result) -> Result | None:
        return result


class ActionModule(ActionBase):
    def run(self, tmp: None = None, task_vars: dict = None) -> dict[str, typing.Any]:
        args = self._build_args()
        task_vars_wrapper = TaskVars(self._templar, task_vars)
        result = Result()

        if task_vars_wrapper["policy.destructive"] is True:
            tasks_mapping = {
                UninstallTask: args.wipe,
                WipeTask: args.wipe,
                InstallTask: args.install,
            }
        else:
            tasks_mapping = {InstallTask: args.install}

        for task_class, tools in tasks_mapping.items():
            for tool in tools:
                premature_result = self._handle_tool(
                    result, task_vars_wrapper, task_class, tool
                )
                if premature_result is not None:
                    return premature_result

        return result

    def _build_args(self) -> Arguments:
        spec = {
            "wipe": {
                "type": "list",
                "required": False,
                "elements": "str",
                "description": [
                    "A list of tools to wipe.",
                    "Has not affect if `policy.destructive` is false.",
                ],
            },
            "install": {
                "type": "list",
                "required": False,
                "elements": "str",
                "description": [
                    "A list of tools to install.",
                    "Must be in the form of tool@version.",
                ],
            },
        }

        _, raw_args = self.validate_argument_spec(
            argument_spec=spec,
            required_one_of=[["install", "wipe"]],
        )

        return Arguments(**dict(filter(lambda kv: kv[1] is not None, raw_args.items())))

    def _handle_tool(
        self,
        result: Result,
        task_vars: TaskVars,
        task_class: typing.Type[Task],
        tool: str,
    ) -> Result | None:
        task = task_class(task_vars, tool)
        message = "({}) => '{}'".format(*task.info())
        if self._task.check_mode:
            task_result = None
        else:
            module_name, module_args = task.execution_context()
            task_result = task.execution_wrap(
                self._execute_module(
                    module_name=module_name,
                    module_args=module_args,
                    task_vars=task_vars.raw,
                )
            )

        match task_result:
            case {"failed": True} as failed_result:
                self._display.display(f"failed: {message}", COLOR_ERROR)
                return failed_result
            case {"changed": True}:
                result["changed"] = True
                self._display.display(f"changed: {message}", COLOR_CHANGED)
            case {}:
                self._display.display(f"ok: {message}", COLOR_OK)

        return None
