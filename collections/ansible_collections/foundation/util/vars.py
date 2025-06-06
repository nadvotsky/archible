import typing

from ansible.template import Templar
from ansible.errors import AnsibleActionFail

from ansible_collections.foundation.util.types import TaskVars


def var_lookup(templar: Templar, task_vars: TaskVars, key: str) -> typing.Any:
    value = templar.template(task_vars.get(key))
    if value is None:
        raise AnsibleActionFail(f"Fallback variable '{key}' is required")

    return value
