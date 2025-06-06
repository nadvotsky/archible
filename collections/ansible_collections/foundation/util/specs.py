import typing

from ansible.module_utils.common.arg_spec import ArgumentSpecValidator
from ansible.errors import AnsibleActionFail


def validate_spec(spec: dict, obj: typing.Any, one_of: list[str] = None) -> typing.Any:
    validator = ArgumentSpecValidator(spec, required_one_of=([one_of] if one_of is not None else None))

    result = validator.validate(obj)
    if len(result.errors.errors):
        raise AnsibleActionFail(result.error_messages)

    obj.update(result.validated_parameters)

    return obj
