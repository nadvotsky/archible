import typing

import dataclasses


@dataclasses.dataclass
class Result:
    skipped: bool | None = False
    changed: bool | None = False
    failed: bool | None = False
    msg: str | None = None


class RawResult(typing.TypedDict):
    skipped: bool | None = None
    changed: bool | None = None
    failed: bool | None = None
    msg: str | None = None


type TaskVars = typing.Mapping[str, typing.Any]
