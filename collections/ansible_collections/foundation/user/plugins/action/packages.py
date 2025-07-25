#
# foundation.user.env - add and remove user packages via mise version manager.
#
# Follow the project README for more information.
#

import typing

import dataclasses
import re
import os.path

from ansible.plugins.action import ActionBase
from ansible.constants import COLOR_CHANGED, COLOR_OK, COLOR_ERROR

from ansible_collections.foundation.util.types import RawResult, TaskVars
from ansible_collections.foundation.util.specs import validate_spec


class Task(typing.Protocol):
    def info(self) -> tuple[str, str]: ...
    def execution_context(self) -> tuple[str, dict[str, typing.Any]]: ...
    def execution_wrap(self, result: RawResult) -> RawResult | None: ...


class UninstallTask(Task):
    def __init__(self, home: str, tool: str, version: str):
        self.cmdline = (
            "/usr/bin/mise",
            "uninstall",
            "--yes",
            "--all",
            f"{tool}@{version}",
        )

    def info(self) -> tuple[str, str]:
        return "uninstall", " ".join(self.cmdline)

    def execution_context(self) -> tuple[str, dict[str, typing.Any]]:
        return "ansible.builtin.command", dict(argv=self.cmdline)

    def execution_wrap(self, result: RawResult) -> RawResult | None:
        if result.get("failed") is True:
            return None

        return result


class WipeTask(Task):
    TOOL_NAME_REGEX = re.compile(r"[:\/]")

    def __init__(self, home: str, tool: str, version: str):
        self.path = os.path.join(home, self.TOOL_NAME_REGEX.sub("-", tool), version)

    def info(self) -> tuple[str, str]:
        return "wipe", self.path

    def execution_context(self) -> tuple[str, dict[str, typing.Any]]:
        return "ansible.builtin.file", dict(path=self.path, state="absent")

    def execution_wrap(self, result: RawResult) -> RawResult | None:
        return result


class XDGWipeTask(WipeTask):
    def __init__(self, home: str, tool: str, version: str):
        super().__init__(os.path.join(home, ".local/share/mise/installs"), tool, version)


class DOTWipeTask(WipeTask):
    def __init__(self, home: str, tool: str, version: str):
        super().__init__(os.path.join(home, ".mise/installs"), tool, version)


class InstallTask(Task):
    def __init__(self, home: str, tool: str, version):
        self.cmdline = ["/usr/bin/mise", "install", f"{tool}@{version}"]

    def info(self) -> tuple[str, str]:
        return "install", " ".join(self.cmdline)

    def execution_context(self) -> tuple[str, dict[str, typing.Any]]:
        return "ansible.builtin.command", dict(argv=self.cmdline)

    def execution_wrap(self, result: RawResult) -> RawResult | None:
        return result


@dataclasses.dataclass
class Context:
    home: str
    wipe: typing.Literal["never", "always"]
    remove: list[str] = dataclasses.field(default_factory=list)
    install: list[str] = dataclasses.field(default_factory=list)


class ActionModule(ActionBase):
    def run(self, tmp: None = None, task_vars: TaskVars = None) -> RawResult:
        ctx, result = self._build_context(), RawResult()

        tasks: list[tuple[Task, tuple[str]]] = []
        tasks.append((UninstallTask, ctx.remove))

        if ctx.wipe == "always":
            tasks.append((XDGWipeTask, ctx.remove))
            tasks.append((DOTWipeTask, ctx.remove))

        tasks.append((InstallTask, ctx.install))

        for task_class, tools in tasks:
            for tool in tools:
                tool, _, version = tool.partition("@")
                early_result = self._handle_tool(task_class(ctx.home, tool, version), task_vars, result)
                if early_result is not None:
                    return early_result

        return result

    def _build_context(self) -> Context:
        _, raw_args = self.validate_argument_spec(
            argument_spec={
                "home": {
                    "type": "path",
                    "required": True,
                },
                "wipe": {
                    "type": "str",
                    "choice": ["always", "never"],
                },
            },
        )
        raw_vars = validate_spec(
            spec={
                "install": {
                    "type": "list",
                    "required": False,
                    "elements": "str",
                    "description": [
                        "A list of tools to install.",
                        "Must be in the form of tool@version.",
                    ],
                },
                "remove": {
                    "type": "list",
                    "required": False,
                    "elements": "str",
                    "description": ["A list of tools to uninstall."],
                },
            },
            obj=self._templar.template(self._task.vars),
            one_of=["install", "remove"],
        )

        context_kwargs = dict(filter(lambda kv: kv[1] is not None, (raw_args | raw_vars).items()))
        return Context(**context_kwargs)

    def _handle_tool(
        self,
        task: InstallTask,
        task_vars: TaskVars,
        result: RawResult,
    ) -> RawResult | None:
        message = "({}) => '{}'".format(*task.info())

        if self._task.check_mode:
            self._display.display(f"ok: {message}", COLOR_OK)
            task_result = None
        else:
            module_name, module_args = task.execution_context()
            task_result = task.execution_wrap(
                self._execute_module(
                    module_name=module_name,
                    module_args=module_args,
                    task_vars=task_vars,
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
