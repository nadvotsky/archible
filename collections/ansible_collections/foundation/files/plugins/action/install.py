#
# foundation.files.install - action plugin for batched file management with wiping support.
#
# Follow the project README for more information.
#

import typing

import os.path
import dataclasses
import enum
import itertools
import functools

from ansible.plugins.action import ActionBase
from ansible.errors import AnsibleActionFail
from ansible.constants import COLOR_SKIP, COLOR_CHANGED, COLOR_OK, COLOR_ERROR

from ansible_collections.foundation.util.types import (
    Result,
    RawResult,
    TaskVars,
)
from ansible_collections.foundation.util.dispatch import ansible_dispatch
from ansible_collections.foundation.util.specs import validate_spec


DEFAULTS_SPECS = {
    "base": {
        "type": "path",
        "required": False,
    },
    "wipe": {
        "type": "str",
        "default": "never",
        "choices": ["never", "always"],
    },
    "create": {
        "type": "bool",
        "default": False,
    },
    "perms": {
        "type": "str",
        "required": False,
    },
}

TARGET_SPECS = {
    "dir": {
        "type": "path",
        "required": False,
    },
    "file": {
        "type": "path",
        "required": False,
    },
    "copy": {
        "type": "str",
        "required": False,
    },
    "content": {
        "type": "path",
        "required": False,
    },
    "template": {
        "type": "path",
        "required": False,
    },
    "link": {
        "type": "path",
        "required": False,
    },
    "url": {
        "type": "str",
        "required": False,
    },
    "wipe": {
        "type": "str",
        "required": False,
        "choices": ["never", "always"],
    },
    "create": {
        "type": "bool",
        "required": False,
    },
    "perms": {
        "type": "str",
        "required": False,
    },
}


#
# Assertations methods. Note that validation in not enforced, and will be ignored in case of `None` values.
#
class Assertations:
    @staticmethod
    def perms_mod(value: str | None) -> str | None:
        if not value:
            return value

        if not value.isdigit() or len(value) != 3:
            raise AnsibleActionFail(f"Permission expression '{value}' must define numeric chmod")

        return value

    @staticmethod
    def base(value: str | None) -> str | None:
        if value is not None and not os.path.isabs(value):
            raise AnsibleActionFail(f"Base directory '{value}' must be absolute")

        return value

#
# Defaults provides fallback properties for targets. During initialization, empty values are allowed and will not raise
#  errors. This lets targets either override parameters explicitly or omit them entirely.
#
class Defaults:
    def __init__(self, mapping: dict):
        self._mapping = mapping
        Assertations.base(self._mapping["base"])

        perms = tuple((self._mapping["perms"] or "").split(":", maxsplit=3))
        self._perms = {
            k: perms[i] if i < len(perms) else None for i, k in enumerate(("dirmod", "filemod", "owner", "group"))
        }

        #
        # Try to validate syntax even if target may not use defaults.
        #
        Assertations.perms_mod(self._perms["dirmod"])
        Assertations.perms_mod(self._perms["filemod"])

    @functools.cached_property
    def base(self) -> str:
        value: str | None = self._mapping["base"]
        if value is None:
            raise AnsibleActionFail("Base directory is required")

        return value

    @functools.cached_property
    def wipe(self) -> str:
        value = self._mapping["wipe"]
        if value not in ("never", "always"):
            raise AnsibleActionFail("Wipe police only supports never or always")

        return value

    @functools.cached_property
    def create(self) -> bool:
        return self._mapping["create"]

    def _perms_getter(self, key: str, pretty_name: str) -> str:
        if self._perms[key] is None:
            raise AnsibleActionFail(f"Permission expression is missing {pretty_name} (dir:file:own:grp)")

        return self._perms[key]

    @functools.cached_property
    def perms_dirmod(self) -> str:
        return self._perms_getter("dirmod", "directory chmod")

    @functools.cached_property
    def perms_filemod(self) -> str:
        return self._perms_getter("filemod", "file chmod")

    @functools.cached_property
    def perms_owner(self) -> str:
        return self._perms_getter("owner", "target owner")

    @functools.cached_property
    def perms_group(self) -> str:
        return self._perms_getter("group", "target group")


#
# Wrapper around target operation, with informational message hints.
#
@dataclasses.dataclass
class Context:
    name: str
    dispatch: str
    raw: typing.Mapping[str, typing.Any]

    dst_attr: str
    src_attr: str | None = None

    #
    # Formats an operation message using attributes separated by '=>' and filesystem permissions.
    #
    def format_message(self) -> str:
        def format_part(*items: list[str | None], sep: str = " ") -> str:
            return sep.join(filter(None, items))

        message_parts = [
            format_part(self.raw.get(self.src_attr), self.raw[self.dst_attr], sep=" => "),
            format_part(
                self.raw.get("mode"),
                self.raw.get("owner"),
                self.raw.get("group"),
                sep=":",
            ),
        ]

        return " ".join(filter(None, message_parts))


class TargetKind(enum.Enum):
    FILE = 1
    DIR = 2


class TargetProcessor:
    #
    # Common actions are not considered unique for targets and therefore are excluded from no-op assertions.
    #
    COMMON_ACTIONS: typing.ClassVar[typing.Sequence[str]] = ("wipe", "create")
    DIR_ACTIONS: typing.ClassVar[typing.Sequence[str]] = ["link"]
    FILE_ACTIONS: typing.ClassVar[typing.Sequence[str]] = (
        "link",
        "copy",
        "template",
        "content",
        "url",
    )
    ALL_ACTIONS: typing.ClassVar[typing.Sequence[str]] = set((*DIR_ACTIONS, *FILE_ACTIONS))

    @staticmethod
    def postprocess_path(path: str | None, defaults: Defaults) -> str:
        if path is None:
            raise AnsibleActionFail("Target must define either directory or file only")
        elif os.path.isabs(path):
            return os.path.normpath(path)
        elif not path.startswith("./"):
            raise AnsibleActionFail("Relative path '{}' must start with './'".format(path))

        return os.path.normpath(os.path.join(defaults.base, path))

    @classmethod
    def postprocess_actions(cls, model: object, kind: TargetKind) -> TargetKind:
        def count_defined_actions(attrs: typing.Sequence[str]) -> int:
            return sum((getattr(model, attr) is not None for attr in attrs))

        #
        # Verify unsupported actions first.
        #
        allowed_actions = cls.DIR_ACTIONS if kind == TargetKind.DIR else cls.FILE_ACTIONS
        forbidden_actions = cls.ALL_ACTIONS.difference(allowed_actions)
        if count_defined_actions(forbidden_actions) > 0:
            raise AnsibleActionFail(
                "Actions '{}' are not supported by '{}'".format(
                    ", ".join(forbidden_actions),
                    kind,
                )
            )

        #
        # Then verify allowed actions.
        #
        allowed = count_defined_actions(allowed_actions)
        if allowed > 1:
            raise AnsibleActionFail("More than one action '{}'".format(", ".join(allowed_actions)))

        #
        # Otherwise, check if target requested anything at all.
        #
        common = count_defined_actions(cls.COMMON_ACTIONS)
        if allowed + common == 0:
            raise AnsibleActionFail("Target is no-op")

        return kind

    @staticmethod
    def postprocess_perms(perms: str | None) -> tuple[str | None, str | None, str | None]:
        if perms is None:
            return (None, None, None)

        iterator = iter(perms.split(":", maxsplit=2))
        return (
            Assertations.perms_mod(next(iterator)),
            next(iterator, None),
            next(iterator, None)
        )


@dataclasses.dataclass
class Target:
    wipe: bool
    create: bool
    perms: tuple[str | None, str | None, str | None]

    copy: str | None = None
    template: str | None = None
    content: str | None = None
    link: str | None = None
    url: str | None = None

    dir: dataclasses.InitVar[str | None] = None
    file: dataclasses.InitVar[str | None] = None

    defaults: Defaults = None
    kind: TargetKind = dataclasses.field(init=False)
    path: str = dataclasses.field(init=False)

    def __post_init__(self, _dir: str | None, _file: str | None) -> None:
        try:
            self.path = TargetProcessor.postprocess_path(_dir or _file, self.defaults)

            if self.create is None:
                self.create = self.defaults.create

            if self.wipe is None or self.wipe == "auto":
                self.wipe = self.defaults.wipe

            self.kind = TargetProcessor.postprocess_actions(
                self, TargetKind.DIR if _dir is not None else TargetKind.FILE
            )
            self.perms = TargetProcessor.postprocess_perms(self.perms)
        except AnsibleActionFail as fail:
            raise AnsibleActionFail(
                "Target '{}' failed: {}".format(_dir or _file, str(fail)),
            )

    @functools.cached_property
    def _perms_raw(self) -> dict:
        mode, owner, group = self.perms

        if self.kind == TargetKind.FILE:
            mode = Assertations.perms_mod(mode or self.defaults.perms_filemod)
        elif self.kind == TargetKind.DIR:
            mode = Assertations.perms_mod(mode or self.defaults.perms_dirmod)
        else:
            raise AnsibleActionFail(f"Unreachable kind {self.kind}")

        #
        # Lazy evaluation: defaults are only evaluated if needed.
        #
        owner = owner or self.defaults.perms_owner
        group = group or self.defaults.perms_group

        return dict(mode=mode, owner=owner, group=group)

    def build_wipe_context(self) -> Context:
        return Context(
            name="wipe",
            dispatch="ansible.builtin.file",
            dst_attr="path",
            raw=dict(path=self.path, state="absent", follow="yes"),
        )

    def build_create_context(self) -> Context:
        return Context(
            name="create",
            dispatch="ansible.builtin.file",
            dst_attr="path",
            raw=self._perms_raw | dict(path=self.path, state="directory" if self.kind == TargetKind.DIR else "touch"),
        )

    def build_link_context(self) -> Context:
        return Context(
            name="link",
            dispatch="ansible.builtin.file",
            dst_attr="dest",
            src_attr="src",
            raw=dict(src=self.link, dest=self.path, state="link", follow=False, force=True),
        )

    def build_touch_context(self) -> Context:
        return Context(
            name="touch",
            dispatch="ansible.builtin.file",
            dst_attr="path",
            raw=self._perms_raw | dict(path=self.path, state="touch"),
        )

    def build_copy_context(self) -> Context:
        return Context(
            name="create",
            dispatch="ansible.builtin.copy",
            dst_attr="dest",
            src_attr="src",
            raw=self._perms_raw | dict(src=self.copy, dest=self.path),
        )

    def build_content_context(self) -> Context:
        return Context(
            name="content",
            dispatch="ansible.builtin.copy",
            dst_attr="dest",
            raw=self._perms_raw | dict(content=self.content, dest=self.path),
        )

    def build_template_context(self) -> Context:
        return Context(
            name="template",
            dispatch="ansible.builtin.template",
            dst_attr="dest",
            src_attr="src",
            raw=self._perms_raw | dict(src=self.template, dest=self.path, lstrip_blocks=True, trim_blocks=True),
        )

    def build_url_context(self) -> Context:
        return Context(
            name="url",
            dispatch="ansible.builtin.uri",
            dst_attr="dest",
            src_attr="url",
            raw=self._perms_raw | dict(url=self.url, dest=self.path, creates=self.path, follow_redirects="all"),
        )


class ActionModule(ActionBase):
    def run(self, tmp: None = None, task_vars: TaskVars = None) -> RawResult:
        defaults = Defaults(self.validate_argument_spec(DEFAULTS_SPECS)[1])
        raw_vars = validate_spec(
            {
                "targets": {
                    "type": "list",
                    "required": True,
                    "elements": "dict",
                    "options": TARGET_SPECS,
                },
            },
            self._templar.template(self._task.vars),
        )

        targets = [Target(defaults=defaults, **raw_target) for raw_target in raw_vars["targets"]]

        return self._process_targets(targets, task_vars, Result())

    def _accumulate_result(self, context: Context, result: RawResult, acc: Result) -> None:
        match result:
            case {"failed": True}:
                acc.failed, acc.msg = True, "Failed to process target"
                color = COLOR_ERROR
            case {"changed": True}:
                acc.changed = True
                color = COLOR_CHANGED
            case {"skipped": True}:
                acc.skipped = True
                color = COLOR_SKIP
            case _:
                color = COLOR_OK

        self._display.display("{}: {}".format(context.name, context.format_message()), color)

    def _process_targets(
        self,
        targets: typing.Sequence[Target],
        task_vars: TaskVars,
        result: Result,
    ) -> RawResult:
        for context, raw_result in itertools.chain(
            self._handle_early_operations(targets, task_vars),
            self._handle_target_operations(targets, task_vars),
        ):
            self._accumulate_result(context, raw_result, result)
            if result.failed is True:
                self._display.display(raw_result.get("msg"), COLOR_ERROR)
                break

        return dataclasses.asdict(result)

    def _handle_early_operations(
        self,
        targets: typing.Sequence[Target],
        task_vars: TaskVars,
    ) -> typing.Generator[tuple[Context, RawResult]]:
        wipe_history: set[str] = set()
        for target in targets:
            #
            # Do not wipe any nested directories if parent has already been wiped.
            #
            if target.wipe == "always" and not any(
                (os.path.commonpath((target.path, hist)) == hist for hist in wipe_history)
            ):
                yield self._ansible_dispatch(target.build_wipe_context(), task_vars)
                wipe_history.add(target.path)

            if target.create is True and target.kind == TargetKind.DIR:
                yield self._ansible_dispatch(target.build_create_context(), task_vars)

    def _handle_target_operations(
        self,
        targets: list[Target],
        task_vars: TaskVars,
    ) -> typing.Generator[tuple[Context, RawResult]]:
        for target in targets:
            #
            # File creation (touch) is listed first as a fallback, ensuring it will not run if other file-specific
            #  actions are defined.
            #
            context_builder = {
                target.create is True: target.build_create_context,
                target.link is not None: target.build_link_context,
                target.copy is not None: target.build_copy_context,
                target.content is not None: target.build_content_context,
                target.template is not None: target.build_template_context,
                target.url is not None: target.build_url_context,
            }
            if True not in context_builder:
                continue

            context = context_builder[True]()
            #
            # Directory creation is already a part of early operations.
            #
            if context.name == "create" and target.kind == TargetKind.DIR:
                continue

            yield self._ansible_dispatch(context, task_vars)

    def _ansible_dispatch(self, context: Context, task_vars: TaskVars) -> RawResult:
        return context, ansible_dispatch(self, context.dispatch, context.raw, task_vars)
