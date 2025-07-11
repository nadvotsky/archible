import typing

import dataclasses

from ansible.plugins.action import ActionBase
from ansible.errors import AnsibleActionFail
from ansible.constants import COLOR_CHANGED, COLOR_OK, COLOR_ERROR, COLOR_SKIP

from ansible_collections.foundation.util.types import RawResult, TaskVars
from ansible_collections.foundation.util.specs import validate_spec


SPEC = {
    "sync": {
        "type": "bool",
        "required": False,
    },
    "force": {
        "type": "bool",
        "required": False,
    },
}

VARS_SPEC = {
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
}


@dataclasses.dataclass
class Inputs:
    remove: list[str] = dataclasses.field(default_factory=list)
    install: list[str] = dataclasses.field(default_factory=list)

    force: bool = False
    sync: bool = False


class ActionModule(ActionBase):
    def run(self, task_vars: TaskVars) -> RawResult:
        inputs, result = self._validate_specs(), RawResult()

        for stage, (cmdline, ignore_error) in {
            "remove": (self._remove_stage(inputs), True),
            "sync": (self._sync_stage(inputs), False),
            "install": (self._install_stage(inputs), False),
        }.items():
            if cmdline is None:
                continue

            status, color = self._merge_result(result, self._execute_paru(task_vars, cmdline, ignore_error))
            self._display.display("{}: ({}) => '{}'".format(status, stage, " ".join(cmdline)), color)

        return result

    def _validate_specs(self) -> Inputs:
        _, raw_args = self.validate_argument_spec(argument_spec=SPEC)
        raw_vars = validate_spec(VARS_SPEC, self._templar.template(self._task.vars))

        if not raw_args.get("sync"):
            if not any((bool(raw_vars.get(key)) for key in VARS_SPEC.keys())):
                raise AnsibleActionFail("No-op action")

        return Inputs(**{k: v for k, v in (raw_args | raw_vars).items() if v is not None})

    def _remove_stage(self, inputs: Inputs) -> typing.Sequence[str] | None:
        if len(inputs.remove) == 0:
            return None

        return ["--remove", "--recursive", *inputs.remove]

    def _sync_stage(self, inputs: Inputs) -> typing.Sequence[str] | None:
        if inputs.sync is not True:
            return None

        return ["--sync", "--refresh"]

    def _install_stage(self, inputs: Inputs) -> typing.Sequence[str] | None:
        if len(inputs.install) == 0:
            return None

        flags = [] if inputs.force else ["--needed"]
        return ["--sync", *flags, *inputs.install]

    def _execute_paru(
        self,
        task_vars: TaskVars,
        cmdline: typing.Sequence[str],
        ignore_error: bool = False,
    ) -> RawResult:
        if self._task.check_mode:
            return RawResult()

        result: RawResult = self._execute_module(
            module_name="ansible.builtin.command",
            module_args={
                "argv": [
                    "/usr/bin/paru",
                    "--sudoflags",
                    "--stdin",
                    "--noconfirm",
                    *cmdline,
                ],
                "stdin": self._play_context.become_pass,
            },
            task_vars=task_vars,
        )
        if result.get("failed") is True and ignore_error is True:
            return RawResult(skipped=True)

        return result

    def _merge_result(self, source: RawResult, overlay: RawResult) -> tuple[str, str]:
        if overlay.get("failed") is True:
            source.update(overlay)
            return "failed", COLOR_ERROR
        elif overlay.get("changed") is True:
            source["changed"] = True
            return "changed", COLOR_CHANGED
        elif overlay.get("skipped") is True:
            return "skipped", COLOR_SKIP

        return "ok", COLOR_OK
