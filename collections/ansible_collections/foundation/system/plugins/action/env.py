from ansible.plugins.action import ActionBase
from ansible.errors import AnsibleActionFail
from ansible.constants import COLOR_CHANGED, COLOR_OK, COLOR_ERROR

from ansible_collections.foundation.util.types import RawResult, TaskVars


class ActionModule(ActionBase):
    def run(self, tmp: None = None, task_vars: TaskVars = None) -> RawResult:
        result = RawResult(changed=False)

        env = self._task.environment.pop()
        if not isinstance(env, dict):
            raise AnsibleActionFail("This action must be given a dictionary.")
        elif len(env) == 0:
            raise AnsibleActionFail("No-op module invocation.")

        for key, val in env.items():
            if not isinstance(val, str):
                raise AnsibleActionFail(f"Variable {key} have got to be a string")

            failure, changed = self._do_line_in_file(task_vars, key, val)
            if failure is not None:
                return failure

            result["changed"] = result["changed"] or changed

        return result

    def _do_line_in_file(self, task_vars: TaskVars, key: str, value: str) -> tuple[RawResult | None, bool]:
        kv = f"{key}={value}"
        result = (
            self._execute_module(
                module_name="ansible.builtin.lineinfile",
                module_args=dict(dest="/etc/environment", regexp="^{}$".format(key), line=kv),
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
