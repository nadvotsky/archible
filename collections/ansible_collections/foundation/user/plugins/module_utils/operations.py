import typing

import dataclasses
import os.path

from ansible.errors import AnsibleError


class Conclusion:
    DS_RESOLVED, DS_SKIPPED = 2 << 1, 2 << 2
    OP_NONE, OP_WIPE, OP_LINK = 0, 2 << 1, 2 << 2

    def __init__(self, descriptor: int, operation: int, value: str, extra: str = None):
        self.descriptor = descriptor
        self.operation = operation
        self.value = value
        self.extra = extra


@dataclasses.dataclass
class OperationContext:
    side_name: str
    descriptor: int
    default_path: str
    wipe: str


class Operations:
    WIPE = ("never", "always")
    WIPE_CHAIN = (*WIPE, "auto")

    def __init__(self, side: str, wipe: str):
        self._side = side
        if self._side not in ["xdg", "dot"]:
            raise AnsibleError("Layout accepts only 'xdg' or 'dot'")

        self._wipe_fallback = wipe
        if self._wipe_fallback is not None and self._wipe_fallback not in self.WIPE:
            return AnsibleError(f"Fallback wipe must be {self.WIPE}, not {self._wipe_fallback}")

    @staticmethod
    def _validate_dict_keys(dictionary: dict, keys: tuple[str]) -> dict:
        if interdit := set(dictionary.keys()).difference(keys):
            raise AnsibleError(f"Unsupported property {interdit}, expected {keys}")

        return dictionary

    @staticmethod
    def _validate_dict_value(dictionary: dict, key: str) -> typing.Any:
        if key not in dictionary:
            raise AnsibleError(f"Property '{key}' must be defined")
        elif not isinstance(value := dictionary[key], str):
            raise AnsibleError(f"Property '{key}' ({value}) must be of string type")

        return value

    @staticmethod
    def _validate_path(context: str, value: str) -> str | None:
        if not os.path.isabs(value):
            raise AnsibleError(f"Property '{context}' ({value}) has to point to absolute path")

        return value

    def _validate_wipe(self, choice: dict) -> str | AnsibleError:
        explicit = choice.get("wipe")
        if explicit is not None:
            if explicit not in self.WIPE_CHAIN:
                return AnsibleError(f"Wipe policy must be either of {self.WIPE_CHAIN}")
            elif explicit in self.WIPE:
                return explicit

        if self._wipe_fallback is None:
            return AnsibleError("Fallback wipe variable must be specified")
        elif self._wipe_fallback not in self.WIPE:
            return AnsibleError(f"Fallback variable allows only {self.WIPE}")

        return self._wipe_fallback

    @staticmethod
    def _evaluate_conclusions(ctx: OperationContext, path: str) -> typing.Sequence[Conclusion]:
        ret = [Conclusion(ctx.descriptor, Conclusion.OP_NONE, path)]
        if ctx.wipe == "always":
            ret.append(Conclusion(ctx.descriptor, Conclusion.OP_WIPE, path))

        return ret

    @classmethod
    def _evaluate_link(
        cls,
        ctx: OperationContext,
        link: typing.Any,
    ) -> typing.Sequence[Conclusion]:
        if not isinstance(link, str):
            raise AnsibleError(f"Property '{ctx.side_name}.link' needs to be string")

        return (
            *cls._evaluate_conclusions(ctx, cls._validate_path(f"{ctx.side_name}.link", link)),
            Conclusion(ctx.descriptor, Conclusion.OP_LINK, link, ctx.default_path),
        )

    @classmethod
    def _evaluate_side(
        cls,
        ctx: OperationContext,
        side: dict | str,
    ) -> typing.Sequence[Conclusion]:
        if isinstance(side, str):
            return cls._evaluate_conclusions(ctx, cls._validate_path(ctx.side_name, side))
        else:
            cls._validate_dict_keys(side, ["link"])

        return cls._evaluate_link(ctx, side["link"])

    def lookup(self, choice: dict) -> typing.Sequence[Conclusion]:
        choice = self._validate_dict_keys(choice, ("wipe", "default", "xdg", "dot"))

        default_path = self._validate_path("default", self._validate_dict_value(choice, "default"))
        wipe = self._validate_wipe(choice)

        conclusions: list[Conclusion] = []
        for side in ("xdg", "dot"):
            if side not in choice:
                continue

            ctx = OperationContext(
                side,
                Conclusion.DS_RESOLVED if self._side == side else Conclusion.DS_SKIPPED,
                default_path,
                wipe,
            )
            conclusions.extend(self._evaluate_side(ctx, choice[side]))

        if not any((True for c in conclusions if c.descriptor == Conclusion.DS_RESOLVED)):
            resolve_ctx = OperationContext(
                self._side,
                Conclusion.DS_RESOLVED,
                default_path,
                wipe,
            )

            return self._evaluate_conclusions(resolve_ctx, default_path)

        return conclusions
