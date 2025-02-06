import os.path
import dataclasses
import typing
import enum
import itertools

from ansible.plugins.action import ActionBase
from ansible.errors import AnsibleActionFail
from ansible.playbook.task import Task

from ansible.constants import COLOR_CHANGED, COLOR_OK, COLOR_ERROR

from ansible.plugins.loader import action_loader


DEFAULTS_SPEC = {
    "base": {
        "type": "path",
        "required": False,
        "description": [
            "The base path for all targets that are not absolute.",
        ],
    },
    "wipe": {
        "type": "bool",
        "required": False,
        "default": False,
        "description": [
            "Ignored when `policy.destructive` is false.",
            "For directory targets, wipe the provided directory.",
            "For file targets, wipe the parent directory.",
        ],
    },
    "create": {
        "type": "bool",
        "required": False,
        "default": True,
        "description": [
            "For directory targets, create the provided directory.",
            "For file targets, create the parent directory, and empty file if no other operation specified.",
        ],
    },
    "owner": {
        "type": "str",
        "required": False,
        "description": [
            "Owner of the filesystem objects (including parent directory for file targets).",
        ],
    },
    "group": {
        "type": "str",
        "required": False,
        "description": [
            "Group of the filesystem objects (including parent directory for file targets).",
        ],
    },
    "filemode": {
        "type": "str",
        "required": False,
        "default": "0644",
        "description": [
            "File targets permissions.",
        ],
    },
    "dirmode": {
        "type": "str",
        "required": False,
        "default": "0755",
        "description": [
            "For directory targets, set the provided directory permissions.",
            "Fir file targets, set the parent directory permissions.",
        ],
    },
}

TARGETS_SPEC = {
    "dir": {
        "type": "str",
        "required": False,
        "description": [
            "An absolute or relative path to the directory target.",
        ],
    },
    "file": {
        "type": "str",
        "required": False,
        "description": [
            "An absolute or relative path to the file target.",
        ],
    },
    "src": {
        "type": "str",
        "required": False,
        "description": [
            "A file from this playbook to copy to the file target.",
        ],
    },
    "content": {
        "type": "str",
        "required": False,
        "description": [
            "A string content to write to the file target.",
        ],
    },
    "template": {
        "type": "str",
        "required": False,
        "description": [
            "A template to render to the file target.",
        ],
    },
    "link": {
        "type": "str",
        "required": False,
        "description": [
            "The control node filesystem object to link to the target.",
        ],
    },
    "wipe": {
        "type": "bool",
        "required": False,
        "description": [
            "This setting has the same meaning as the `defaults.wipe` but on the target level.",
        ],
    },
    "create": {
        "type": "bool",
        "required": False,
        "description": [
            "This setting has the same meaning as the `defaults.create` but on the target level.",
        ],
    },
    "owner": {
        "type": "str",
        "required": False,
        "description": [
            "This setting has the same meaning as the `defaults.owner` but on the target level.",
        ],
    },
    "group": {
        "type": "str",
        "required": False,
        "description": [
            "This setting has the same meaning as the `defaults.group` but on the target level.",
        ],
    },
    "filemode": {
        "type": "str",
        "required": False,
        "description": [
            "This setting has the same meaning as the `defaults.filemode` but on the target level.",
        ],
    },
    "dirmode": {
        "type": "str",
        "required": False,
        "description": [
            "This setting has the same meaning as the `defaults.dirmode` but on the target level.",
        ],
    },
    "base": {
        "type": "str",
        "required": False,
        "description": [
            "This setting has the same meaning as the `defaults.base` but on the target level.",
        ],
    },
}


@dataclasses.dataclass
class Context:
    name: str
    dest: str
    raw: typing.Mapping[str, typing.Any]

    src: str | None = None
    perm: bool = False

    def format_message(self) -> str:
        def format_part(*items: list[str | None], sep: str = " ") -> str:
            return sep.join(filter(None, items))

        message_parts = [
            format_part(self.raw.get(self.src), self.raw[self.dest], sep=" => "),
        ]
        if self.perm is True:
            message_parts.append(format_part(str(self.raw["mode"])))
            message_parts.append(
                format_part(self.raw["owner"], self.raw["group"], sep=":")
            )

        return " ".join(message_parts)


class TargetKind(enum.Enum):
    FILE = 1
    DIR = 2


@dataclasses.dataclass
class Target:
    EARLY_ATTRS: typing.ClassVar[typing.Sequence[str]] = ("wipe", "create")
    KIND_ATTRS: typing.ClassVar[
        typing.Mapping[TargetKind, tuple[typing.Sequence[str], typing.Sequence[str]]]
    ] = {
        TargetKind.DIR: (
            ("link",),
            ("src", "template", "content", "link", "touch"),
        ),
        TargetKind.FILE: (
            ("link", "src", "template", "content", "link", "touch"),
            tuple(),
        ),
    }

    base: dataclasses.InitVar[str]
    wipe: bool
    create: bool
    owner: str | int
    group: str | int
    filemode: str
    dirmode: str

    kind: TargetKind = dataclasses.field(init=False)
    path: str = dataclasses.field(init=False)
    directory: str = dataclasses.field(init=False)

    dir: dataclasses.InitVar[str | None] = None
    file: dataclasses.InitVar[str | None] = None

    src: str | None = None
    template: str | None = None
    content: str | None = None
    link: str | None = None
    touch: bool | None = None

    def __post_init__(self, base: str, _dir: str, file: str) -> None:
        if len(tuple(filter(None, (_dir, file)))) != 1:
            raise AnsibleActionFail("Either directory or file target expected.")

        self.kind = TargetKind.FILE if file is not None else TargetKind.DIR
        self.path = file if self.kind == TargetKind.FILE else _dir
        if not os.path.isabs(self.path):
            if base is None:
                raise AnsibleActionFail(
                    "A base is expected for relative '{}'.".format(self.path)
                )
            elif not os.path.isabs(base):
                raise AnsibleActionFail("Non-absolute base '{}'.".format(base))

            self.path = os.path.join(base, self.path)
        self.directory = (
            os.path.dirname(self.path) if self.kind == TargetKind.FILE else self.path
        )

        early, allowed, forbidden = (
            len(tuple(filter(None, (getattr(self, attr) for attr in attrs))))
            for attrs in (self.EARLY_ATTRS, *self.KIND_ATTRS[self.kind])
        )
        if sum((early, allowed, forbidden)) == 0:
            raise AnsibleActionFail("Target '{}' is no-op.".format(self.path))
        elif forbidden > 0:
            raise AnsibleActionFail(
                "Target '{}' ({}) does not support '{}'.".format(
                    self.path, self.kind, ", ".join(self.KIND_ATTRS[self.kind][1])
                )
            )
        elif allowed > 1:
            raise AnsibleActionFail(
                "Target '{}' ({}) has more than one operation '{}'.".format(
                    self.path, self.kind, ", ".join(self.KIND_ATTRS[self.kind][0])
                )
            )

    def _build_common_raw(self, conjuction: dict) -> dict:
        return {
            "owner": self.owner,
            "group": self.group,
            "mode": self.filemode,
            **conjuction,
        }

    def build_wipe_context(self) -> Context:
        raw = dict(path=self.directory, state="absent")
        return Context(name="wipe", dest="path", raw=raw)

    def build_create_context(self) -> Context:
        raw = self._build_common_raw(
            dict(path=self.directory, state="directory", mode=self.dirmode)
        )
        return Context(name="create", dest="path", perm=True, raw=raw)

    def build_src_context(self) -> Context:
        raw = self._build_common_raw(dict(src=self.src, dest=self.path))
        return Context(name="create", dest="dest", src="src", perm=True, raw=raw)

    def build_template_context(self) -> Context:
        raw = self._build_common_raw(
            dict(
                src=self.template, dest=self.path, lstrip_blocks=True, trim_blocks=True
            )
        )
        return Context(name="template", dest="dest", src="src", perm=True, raw=raw)

    def build_content_context(self) -> Context:
        raw = self._build_common_raw(dict(content=self.content, dest=self.path))
        return Context(name="content", dest="dest", perm=True, raw=raw)

    def build_link_context(self) -> Context:
        raw = dict(
            src=self.link, dest=self.path, state="link", follow=False, force=True
        )
        return Context(name="link", dest="dest", src="src", perm=True, raw=raw)

    def build_touch_context(self) -> Context:
        raw = self._build_common_raw(dict(path=self.path, state="touch"))
        return Context(name="touch", dest="path", perm=True, raw=raw)


@dataclasses.dataclass
class Result:
    skipped: bool | None = None
    changed: bool | None = None
    failed: bool | None = None
    msg: str | None = None


type TaskVars = typing.Mapping[str, typing.Any]
type RawResult = typing.Mapping[str, typing.Any]


class Arguments(typing.TypedDict):
    defaults: typing.Mapping[str, typing.Any]
    targets: typing.Mapping[str, typing.Any]


class ActionModule(ActionBase):
    def run(self, tmp: None = None, task_vars: TaskVars = None) -> RawResult:
        result = Result()
        args: Arguments = self.validate_argument_spec(self._build_spec(task_vars))[1]

        if self._task.check_mode:
            return result

        targets = []
        for raw_target in args["targets"]:
            conjuction = args["defaults"] | {
                k: v for k, v in raw_target.items() if v is not None
            }
            targets.append(Target(**conjuction))

        return self._process_targets(task_vars, result, targets)

    def _build_spec(self, task_vars: typing.Mapping[str, typing.Any]):
        def templar(expr):
            return self._templar.template(expr)

        defaults = DEFAULTS_SPEC.copy()

        if self._task._become is True:
            user_name = "root"
        else:
            user_name = templar(task_vars["users"]["user"]["name"])

        defaults["owner"]["default"] = user_name
        defaults["group"]["default"] = user_name

        defaults["base"]["default"] = templar(task_vars["users"]["user"]["config"])

        return {
            "defaults": {
                "type": "dict",
                "required": False,
                "options": defaults,
                "default": {},
            },
            "targets": {
                "type": "list",
                "required": True,
                "elements": "dict",
                "options": TARGETS_SPEC,
            },
        }

    def _process_targets(
        self, task_vars: TaskVars, result: Result, targets: typing.Sequence[Target]
    ) -> RawResult:
        for context, raw_result in itertools.chain(
            self._handle_early_operations(task_vars, targets),
            self._handle_target_operations(task_vars, targets),
        ):
            if raw_result.get("failed") is True:
                result.failed = True
                result.msg = "Failed to process target"
                color = COLOR_ERROR
            elif raw_result.get("changed") is True:
                result.changed = True
                color = COLOR_CHANGED
            else:
                color = COLOR_OK

            self._display.display(
                "{}: {}".format(context.name, context.format_message()), color
            )

            if result.failed is True:
                if self._task._no_log is not True:
                    self._display.display(raw_result.get("msg"), COLOR_ERROR)
                break

        return dataclasses.asdict(result)

    def _handle_early_operations(
        self, task_vars: TaskVars, targets: typing.Sequence[Target]
    ) -> typing.Generator[tuple[Context, RawResult]]:
        wipe_history: set[str] = set()
        create_history: set[str] = set()
        for target in targets:
            if target.wipe is True and not any(
                (
                    os.path.commonpath((target.directory, hist)) == hist
                    for hist in wipe_history
                )
            ):
                yield self._file(task_vars, target.build_wipe_context())
                wipe_history.add(target.directory)

            if target.create is True and target.directory not in create_history:
                yield self._file(task_vars, target.build_create_context())
                create_history.add(target.directory)

    def _handle_target_operations(
        self, task_vars: TaskVars, targets: list[Target]
    ) -> typing.Generator[tuple[Context, RawResult]]:
        for target in targets:
            fn_dict = {
                target.link is not None: (self._file, target.build_link_context),
                target.src is not None: (self._copy, target.build_src_context),
                target.template is not None: (self._template, target.build_template_context),
                target.content is not None: (self._copy, target.build_content_context),
                target.touch is not None: (self._file, target.build_touch_context),
            }
            if True not in fn_dict:
                continue

            underlying_fn, context_fn = fn_dict[True]
            yield underlying_fn(task_vars, context_fn())

    def _execute_action(self, task_vars: TaskVars, name, payload) -> RawResult:
        task = Task.load(
            {name: payload},
            block=self._task,
            loader=self._loader,
            variable_manager=self._task.get_variable_manager(),
        )

        action = action_loader.get(
            name,
            task=task,
            connection=self._connection,
            play_context=self._play_context,
            loader=self._loader,
            templar=self._templar,
            shared_loader_obj=self._shared_loader_obj,
        )
        return action.run(task_vars=task_vars)

    def _file(self, task_vars: TaskVars, context: Context) -> tuple[Context, RawResult]:
        return (
            context,
            self._execute_module(
                "ansible.builtin.file",
                context.raw,
                task_vars=task_vars,
            ),
        )

    def _copy(self, task_vars: TaskVars, context: Context) -> tuple[Context, RawResult]:
        return (
            context,
            self._execute_action(task_vars, "ansible.builtin.copy", context.raw),
        )

    def _template(
        self, task_vars: TaskVars, context: Context
    ) -> tuple[Context, RawResult]:
        return (
            context,
            self._execute_action(task_vars, "ansible.builtin.template", context.raw),
        )
