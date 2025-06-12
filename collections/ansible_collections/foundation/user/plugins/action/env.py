import typing

import dataclasses
import os.path
import base64
import re
import enum

from ansible.plugins.action import ActionBase
from ansible.errors import AnsibleActionFail
from ansible.constants import COLOR_CHANGED, COLOR_OK

from ansible_collections.foundation.util.types import RawResult, TaskVars
from ansible_collections.foundation.util.dispatch import ansible_dispatch


SPEC = {
    "section": {
        "type": "str",
        "required": True,
        "description": [
            "A dedicated section where to put variable",
        ],
    },
    "subs": {
        "type": "dict",
        "required": True,
        "description": ["A dictionary of variables to be substituted, typically user paths"],
    },
    "home": {
        "type": "path",
        "required": True,
        "description": ["User home directory; a special 'subs' fallback case"],
    },
}


@dataclasses.dataclass
class Arguments:
    section: str
    home: str
    subs: typing.Mapping[str, str]


class PAMMode(enum.Enum):
    NONE = enum.auto()
    SECT_BEGIN = enum.auto()
    SECT_BODY = enum.auto()


@dataclasses.dataclass
class PAMEntry:
    section: str

    default: str | None = None
    override: str | None = None

    comments: tuple[str] = tuple()
    inline: str | None = None


class PAM:
    SECT_UNKNOWN = "@unknown"
    EXPR_REGEX = tuple(map(re.compile, (r"(\w+)=([\w{}@$]+)", r'(\w+)="([^"]+)"')))

    def __init__(self):
        self._entries: dict[str, PAMEntry] = {}
        self._sections: dict[str, tuple[str]] = {
            self.SECT_UNKNOWN: tuple(),
        }

        self._mode = PAMMode.NONE
        self._section = self.SECT_UNKNOWN
        self._comments = []

        self._changed = False

    def _add_section(self, name: str, comments: tuple[str]) -> None:
        self._sections[name] = comments
        self._comments = []

    def _add_entry(self, variable: str, entry: PAMEntry) -> None:
        if entry.section not in self._section:
            self._add_section(entry.section, tuple())

        self._entries[variable] = entry
        self._comments = []

    def add_entry(self, variable: str, entry: PAMEntry) -> bool:
        if self._entries.get(variable) == entry:
            return False

        self._add_entry(variable, entry)

        self._changed = True
        return True

    def _process_comments(self, comment: str) -> None:
        if not comment.startswith("#"):
            if self._mode != PAMMode.NONE:
                raise ValueError(f"Unsupported comment '{comment}' for '{self._mode}'")

            return self._comments.append(comment)

        match (comment, self._mode):
            case "#", PAMMode.NONE:
                self._mode = PAMMode.SECT_BEGIN
            case "#", PAMMode.SECT_BODY:
                self._mode = PAMMode.NONE
            case _, PAMMode.SECT_BEGIN:
                self._section = comment.removeprefix("#").strip()
                self._add_section(self._section, tuple(self._comments))
                self._mode = PAMMode.SECT_BODY
            case _:
                raise ValueError(f"Invalid comments transition '{comment}' for '{self._mode}'")

    def _process_expression(self, expression: str, comment: str) -> None:
        if self._mode != PAMMode.NONE:
            raise ValueError(f"Unexpected expression '{expression}' for {self._mode}")
        elif expression.endswith("\\"):
            raise ValueError("Multiline variables are discouraged")

        try:
            variable, values = expression.split(maxsplit=1)
        except ValueError:
            raise ValueError(f"No variable declaration in '{expression}'")

        entry = PAMEntry(
            section=self._section,
            comments=tuple(self._comments),
            inline=comment or None,
        )
        for regex in self.EXPR_REGEX:
            for assign, value in regex.findall(values):
                if assign not in ("OVERRIDE", "DEFAULT"):
                    raise ValueError(f"Variable '{variable}' uses unknown qualifier {assign}")
                setattr(entry, assign.lower(), value)

        if not entry.default and not entry.override:
            raise ValueError(f"Variable '{variable}' has no assigned value")

        return self._add_entry(variable, entry)

    def process(self, string: str) -> None:
        for line in string.splitlines():
            expression, _, comment = line.partition("#")

            if not expression:
                self._process_comments(comment)
            else:
                self._process_expression(expression, comment)

        self._changed = False

    def changed(self) -> bool:
        return self._changed

    def _export_comments(self, comments: tuple[str]) -> typing.Sequence[str]:
        if not comments:
            return ()

        return (f"# {com}" for com in comments)

    def _export_entry(self, variable: str, entry: PAMEntry):
        lines = [variable.ljust(30)]
        for name, value in (
            ("DEFAULT", entry.default),
            ("OVERRIDE", entry.override),
        ):
            if not value:
                continue

            lines.append(f'{name}="{value}"')

        if entry.inline:
            lines.append(f"# {entry.inline}")

        return " ".join(lines)

    def export(self) -> str:
        lines = []
        for section in sorted(self._sections.keys()):
            lines.extend(self._export_comments(self._sections[section]))
            lines.extend(["##", f"## {section}", "##"])

            for variable, entry in self._entries.items():
                if entry.section != section:
                    continue

                lines.extend(self._export_comments(entry.comments))
                lines.append(self._export_entry(variable, entry))

        return "\n".join(lines)


class ActionModule(ActionBase):
    PAM_ENV_CONF = "/etc/security/pam_env.conf"

    def _validate_inputs(self) -> tuple[Arguments, dict]:
        raw_args = self.validate_argument_spec(SPEC)[1]

        args, env = Arguments(**raw_args), self._task.environment.pop()
        for collection, desc in (
            (args.subs, "substitutions"),
            (env, "variables"),
        ):
            mismatch = next((val for val in collection.values() if not isinstance(val, str)), None)
            if mismatch is not None:
                raise AnsibleActionFail(f"Expected {desc} to have only string elements, got '{mismatch}'")

        return args, env

    def _read_pam_env(self, task_vars: TaskVars) -> str:
        result: RawResult = self._execute_module(
            module_name="ansible.builtin.slurp",
            module_args=dict(src=self.PAM_ENV_CONF),
            task_vars=task_vars,
        )
        if result.get("failed"):
            raise AnsibleActionFail("Failed to read pam_env", result)

        return base64.b64decode(result["content"].encode()).decode()

    @staticmethod
    def _do_substitution(string: str, name: str, value: str) -> bool:
        return string.replace(value, "${" + name + "}")
        # try:
        #     if os.path.commonpath([string, value]) == value:
        #         return  + "/" + string[len(value) + 1 :]
        # except ValueError:
        #     pass

    def _write_changes(self, content: str, task_vars: TaskVars) -> RawResult:
        return ansible_dispatch(
            self,
            "ansible.builtin.copy",
            {
                "dest": self.PAM_ENV_CONF,
                "content": content,
                "owner": "root",
                "group": "root",
                "mode": "0644",
            },
            task_vars,
        )

    def _inject_variables(self, pam: PAM, args: Arguments, env: typing.Mapping[str, str]) -> None:
        for key, value in args.subs.items():
            entry = PAMEntry("!important", override=self._do_substitution(value, "HOME", args.home))
            pam.add_entry(key, entry)

        for key, value in env.items():
            effective = value
            for sub_key, sub_value in args.subs.items():
                effective = self._do_substitution(effective, sub_key, sub_value)
            effective = self._do_substitution(effective, "HOME", args.home)

            changed = pam.add_entry(key, PAMEntry(args.section, override=effective))
            self._display.display(
                "{}: ({}) => '{}'".format("changed" if changed else "ok", key, effective),
                COLOR_CHANGED if changed else COLOR_OK,
            )

    def run(self, tmp: None = None, task_vars: TaskVars = None) -> RawResult:
        result = RawResult()
        args, env = self._validate_inputs()

        pam, original = PAM(), self._read_pam_env(task_vars)
        pam.process(original)

        self._inject_variables(pam, args, env)
        if self._task.check_mode is True or not pam.changed():
            return result

        final = pam.export()
        if original == final:
            return result

        return self._write_changes(final, task_vars)
