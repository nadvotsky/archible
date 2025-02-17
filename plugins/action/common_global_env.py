import typing

from ansible.plugins.action import ActionBase
from ansible.constants import COLOR_CHANGED, COLOR_OK, COLOR_ERROR


class Result(typing.TypedDict):
    changed: bool | None = None


class ActionModule(ActionBase):
    def run(self, tmp: None = None, task_vars: dict = None) -> Result:
        result = Result(changed=False)
        for env_mapping in self._task.environment:
            for key, val in env_mapping.items():
                failure, changed = self._do_line_in_file(task_vars, key, val)
                if failure is not None:
                    return failure

                result["changed"] = result["changed"] or changed

        return result

    def _do_line_in_file(
        self, task_vars: dict, key: str, value: typing.Any
    ) -> tuple[Result | None, bool]:
        kv = f"{key}={value}"
        result = (
            self._execute_module(
                module_name="ansible.builtin.lineinfile",
                module_args=dict(
                    dest="/etc/environment", regexp="^{}$".format(key), line=kv
                ),
                task_vars=task_vars,
            )
            if self._task.check_mode is False
            else {}
        )

        for key, (color, return_tuple) in {
            "failed": (COLOR_ERROR, (result, False)),
            "changed": (COLOR_CHANGED, (None, True)),
        }.items():
            if result.get(key) is True:
                self._display.display(f"{key}: ({kv})", color)
                return return_tuple
        else:
            self._display.display(f"ok: ({kv})", COLOR_OK)
            return None, False
