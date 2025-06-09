import typing

import dataclasses
import itertools

from ansible.plugins.action import ActionBase
from ansible.constants import COLOR_CHANGED, COLOR_ERROR, COLOR_OK

from ansible_collections.foundation.util.types import RawResult, TaskVars
from ansible_collections.foundation.util.specs import validate_spec


SPEC = {
    "processes": {
        "type": "list",
        "required": False,
        "elements": "str",
        "description": ["A list of processes to kill."],
    },
    "services": {
        "type": "list",
        "required": False,
        "elements": "str",
        "description": ["A list of services to stop."],
    },
}


@dataclasses.dataclass
class Inputs:
    headless: bool
    processes: list[str] | None
    services: list[str] | None


class ActionModule(ActionBase):
    def run(self, tmp: None = None, task_vars: TaskVars = None) -> RawResult:
        inputs = self._process_inputs()
        for result, status in itertools.chain(
            map(
                lambda process: self._kill_step(process, inputs.headless, task_vars),
                inputs.processes or [],
            ),
            map(
                lambda service: self._stop_step(service, inputs.headless, task_vars),
                inputs.services or [],
            ),
        ):
            if result.get("failed") is True:
                prefix, color = "failed", COLOR_ERROR
            elif result.get("changed") is True:
                prefix, color = "changed", COLOR_CHANGED
            else:
                prefix, color = "ok", COLOR_OK

            self._display.display("{}: {}".format(prefix, status), color)

        return RawResult()

    def _process_inputs(self) -> Inputs:
        _, raw_args = self.validate_argument_spec(argument_spec={"headless": {"type": str, "required": True}})
        variables = validate_spec(SPEC, self._task.vars, one_of=list(SPEC.keys()))

        return Inputs(
            headless=raw_args["headless"],
            processes=variables["processes"],
            services=variables["services"],
        )

    def _kill_step(
        self,
        process: str,
        headless: bool,
        task_vars: TaskVars,
    ) -> typing.Generator[tuple[RawResult, str]]:
        cmd = ["killall", "--process-group", "--wait", process]
        status = "(process) => '{}'".format(" ".join(cmd))

        result = (
            RawResult()
            if headless
            else self._execute_module(
                module_name="ansible.builtin.command",
                module_args=dict(argv=cmd),
                task_vars=task_vars,
            )
        )
        if result.get("rc") == 0:
            return RawResult(changed=True), status

        return result, status

    def _stop_step(self, service: str, headless: bool, task_vars: TaskVars) -> typing.Generator[tuple[str, RawResult]]:
        status = f"(service) => {service}"
        result = (
            RawResult()
            if headless
            else self._execute_module(
                module_name="ansible.builtin.systemd_service",
                module_args=dict(
                    name=service,
                    state="stopped",
                    scope="system" if self._task._become else "user",
                ),
                task_vars=task_vars,
            )
        )

        return result, status
