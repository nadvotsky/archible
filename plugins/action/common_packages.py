import dataclasses
import typing

from ansible.plugins.action import ActionBase
from ansible.constants import COLOR_CHANGED, COLOR_OK, COLOR_ERROR


SPEC = {
    "install": {
        "type": "list",
        "required": False,
        "elements": "str",
    },
    "remove": {
        "type": "list",
        "required": False,
        "elements": "str",
    },
    "sync": {
        "type": "bool",
        "required": False,
    },
    "force": {
        "type": "bool",
        "required": False,
    },
}


class Result(typing.TypedDict):
    changed: typing.NotRequired[bool]
    failed: typing.NotRequired[bool]
    msg: typing.NotRequired[str]


@dataclasses.dataclass
class Arguments:
    remove: list[str] = dataclasses.field(default_factory=list)
    install: list[str] = dataclasses.field(default_factory=list)

    force: bool = False
    sync: bool = False


class ActionModule(ActionBase):
    def run(self, tmp: None = None, task_vars: dict = None) -> dict[str, typing.Any]:
        args = self._validate_specs()
        result = Result()

        for stage, cmdline in {
            "remove": self._remove_stage(args),
            "sync": self._sync_stage(args),
            "install": self._install_stage(args),
        }.items():
            if cmdline is None:
                continue

            color = self._merge_result(result, self._execute_paru(task_vars, cmdline))
            if color != COLOR_ERROR:
                self._display.display(
                    "{}: ({}) => '{}'".format(
                        "changed" if color == COLOR_CHANGED else "ok",
                        stage,
                        " ".join(cmdline),
                    ),
                    color,
                )

        return result

    def _validate_specs(self) -> Arguments:
        _, raw_args = self.validate_argument_spec(
            argument_spec=SPEC,
            required_one_of=[["install", "remove", "sync"]],
        )

        return Arguments(**{k: v for k, v in raw_args.items() if v is not None})

    def _remove_stage(self, args) -> typing.Sequence[str] | None:
        if len(args.remove) == 0:
            return None

        return ["--remove", "--recursive", *args.remove]

    def _sync_stage(self, args) -> typing.Sequence[str] | None:
        if args.sync is not True:
            return None

        return ["--sync", "--refresh"]

    def _install_stage(self, args) -> typing.Sequence[str] | None:
        if len(args.install) == 0:
            return None

        cmdline = [] if args.force else ["--needed"]
        return [*cmdline, *args.install]

    def _execute_paru(self, task_vars: dict, cmdline: typing.Sequence[str]) -> Result:
        if self._task.check_mode:
            return Result()

        return self._execute_module(
            module_name="ansible.builtin.command",
            module_args={
                "argv": [
                    "/usr/bin/paru",
                    "--sudoflags",
                    "--stdin",
                    "--noconfirm",
                    *cmdline,
                ],
                "stdin": self._templar.template(task_vars["ansible_become_password"]),
            },
            task_vars=task_vars,
        )

    def _merge_result(self, source: Result, overlay: Result) -> str:
        if overlay.get("failed") is True:
            source.update(overlay)
            return COLOR_ERROR
        elif overlay.get("changed") is True:
            source["changed"] = True
            return COLOR_CHANGED

        return COLOR_OK
