import typing

import dataclasses


#
# Typed action result. Note the use of False as the default value instead of None, which is required for proper Ansible
#  loop support.
#
@dataclasses.dataclass
class Result:
    skipped: bool | None = False
    changed: bool | None = False
    failed: bool | None = False
    msg: str | None = None

#
# Raw version of the above, but in the form of a dictionary with typing support.
#
class RawResult(typing.TypedDict):
    skipped: bool | None = None
    changed: bool | None = None
    failed: bool | None = None
    msg: str | None = None


#
# Alias to TaskVars for shorted function signatures.
#
type TaskVars = typing.Mapping[str, typing.Any]
