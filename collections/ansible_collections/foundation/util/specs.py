import typing

from ansible.module_utils.common.arg_spec import ArgumentSpecValidator
from ansible.errors import AnsibleActionFail

#
# Similar to the built-in ActionBase.validate_argument_spec functionality, but with support for arbitrary objects.
# This can be used to validate task's variables and environment context.
#
# See also: https://docs.ansible.com/ansible/latest/dev_guide/developing_program_flow_modules.html#argument-spec
#
def validate_spec(spec: dict, obj: typing.Any, one_of: list[str] = None) -> typing.Any:
    validator = ArgumentSpecValidator(spec, required_one_of=([one_of] if one_of is not None else None))

    result = validator.validate(obj)
    if len(result.errors.errors):
        raise AnsibleActionFail(result.error_messages)

    obj.update(result.validated_parameters)

    return obj
