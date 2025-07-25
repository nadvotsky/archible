#
# foundation.user.env - resolve preferred user layout (XDG, dot) dynamically.
#
# Follow the project README for more information.
#

import typing

import dataclasses
import os.path

from ansible.plugins.action import ActionBase
from ansible.constants import COLOR_CHANGED, COLOR_OK
from ansible.errors import AnsibleActionFail

from ansible_collections.foundation.util.types import RawResult, TaskVars
from ansible_collections.foundation.user.plugins.module_utils.operations import (
    Conclusion,
    Operations,
)
from ansible_collections.foundation.util.dispatch import ansible_dispatch


@dataclasses.dataclass
class Arguments:
    wipe: str
    layout: typing.Literal["xdg", "dot"]


#
# Raw operation (dispatch) wrapper that aggregates informational message formatting logic.
#
class DispatchProfile:
    @staticmethod
    def _fmt_primary(value: str) -> str:
        return f"({value})"

    @staticmethod
    def _fmt_secondary(value: str) -> str:
        return f"=> '{value}'"

    def __init__(self, primary: str, secondary: str | None = None):
        self._items = []
        #
        # Allow primary part to be of type `str` and format it with `_fmt_primary` method.
        # Allow secondary part to be of type `str | None` and format it with `_fmt_secondary` method.
        #
        for value, types, formatter in zip(
            (primary, secondary),
            ((str,), (str, type(None))),
            (self._fmt_primary, self._fmt_secondary),
        ):
            if not isinstance(value, types):
                raise AnsibleActionFail(f"Dispatch profile malfunction: wrong attr '{value}'")
            elif value is not None:
                self._items.append((value, formatter))

    def __str__(self) -> str:
        return " ".join([formatter(value) for value, formatter in self._items])


class Dispatch:
    def __init__(self, action: ActionBase, task_vars: TaskVars):
        self._action = action
        self._task_vars = task_vars
        self._state = RawResult()

    def _exec_back(self, result: RawResult, profile: DispatchProfile) -> None:
        if result.get("failed"):
            raise AnsibleActionFail(result)

        if result.get("changed") is True:
            self._state["changed"] = True
            color = COLOR_CHANGED
        else:
            color = COLOR_OK

        self._action._display.display(
            "{}: {}".format(
                "changed" if "changed" in result else "ok",
                str(profile),
            ),
            color,
        )

    def wipe(self, path: str) -> None:
        self._exec_back(
            ansible_dispatch(
                self._action,
                "ansible.builtin.file",
                dict(path=path, follow=False, state="absent"),
                self._task_vars,
            ),
            DispatchProfile(path),
        )

    def link(self, src: str, dst: str) -> None:
        self._exec_back(
            ansible_dispatch(
                self._action,
                "ansible.builtin.file",
                dict(src=src, dest=dst, state="link", follow=False, force=True),
                self._task_vars,
            ),
            DispatchProfile(dst, src),
        )

    def inject(self, key: str, value: str) -> None:
        self._state[key] = value

    def get_state(self) -> RawResult:
        return self._state


class ActionModule(ActionBase):
    @staticmethod
    def _validate_args(container: typing.Any) -> Arguments:
        if not isinstance(container, dict):
            raise AnsibleActionFail("Arguments is expected to be a dict")

        kwargs = {}
        fields = {field.name: field for field in dataclasses.fields(Arguments)}
        #
        # Process both schema and passed keys in one loop.
        #
        for name in set(fields.keys()).union(container.keys()):
            if name in container and name not in fields:
                raise AnsibleActionFail(f"Unknown argument {name}")
            elif name not in container:
                #
                # Set field value as `None` for further dataclass creation.
                #
                kwargs[name] = None
                continue

            #
            # Do value validation through dataclass type hints reflection.
            #
            expected, value = fields[name].type, container[name]
            if typing.get_origin(expected) is typing.Literal:
                expected = typing.get_args(expected)
                if value not in expected:
                    raise AnsibleActionFail(f"Argument {name} must be a part of {expected}")
            elif not isinstance(value, expected):
                raise AnsibleActionFail(f"Argument {name} must follow type {expected}")

            kwargs[name] = value

        #
        # At this stage, `kwargs` contains all values needed to create an `Arguments` instance.
        #
        # If important attributes like `wipe` are omitted (e.g., set to None), the underlying module utility
        #  (`Operations` class) will handle validation.
        #
        return Arguments(**kwargs)

    def _parse_inputs(
        self,
        raw_args: dict,
        raw_variables: dict,
    ) -> tuple[Arguments, typing.Sequence[tuple[str, dict]]]:
        args = self._validate_args(raw_args)

        targets = []
        for key, value in raw_variables.items():
            if not isinstance(value, dict):
                raise AnsibleActionFail(f"Property '{key}' has to be of dict type")
            else:
                targets.append((key, value))

        if len(targets) == 0:
            raise AnsibleActionFail("No-op module")

        return args, targets

    @staticmethod
    def _batched_wipes(dispatch: Dispatch, conclusions: typing.Sequence[Conclusion]) -> None:
        #
        # Sort directories to ensure parents come before children.
        # This enables a single common-path check instead of using a nested loop.
        #
        effective, last = [], None
        for path in sorted((con.value for con in conclusions)):
            if not last or os.path.commonpath((path, last)) != last:
                effective.append(last := path)

        for path in effective:
            dispatch.wipe(path)

    @staticmethod
    def _batched_links(dispatch: Dispatch, conclusions: typing.Sequence[Conclusion]) -> None:
        #
        # Note the link direction: dest => src.
        #
        # This creates a shortcut or view (e.g., ~/.myapp) rather than a transparent redirect, avoiding compatibility
        #  issues with link following and directory creation.
        #
        for con in conclusions:
            dispatch.link(con.extra, con.value)

    def run(self, tmp: None = None, task_vars: TaskVars = None) -> RawResult:
        args, variables = self._parse_inputs(self._task.args, self._templar.template(self._task.vars))
        operations = Operations(args.layout, args.wipe)
        dispatch = Dispatch(self, task_vars)

        wipes, links = [], []
        for name, target in variables:
            for con in operations.lookup(target):
                match con:
                    case Conclusion(descriptor=Conclusion.DS_RESOLVED, operation=Conclusion.OP_NONE):
                        dispatch.inject(name, con.value)

                    case Conclusion(descriptor=Conclusion.DS_RESOLVED, operation=Conclusion.OP_LINK):
                        links.append(con)

                    case Conclusion(operation=Conclusion.OP_WIPE):
                        wipes.append(con)

        #
        # Wipes first, then links. No problem when compatibility link points to non-existent directory.
        #
        self._batched_wipes(dispatch, wipes)
        self._batched_links(dispatch, links)

        return dispatch.get_state()
