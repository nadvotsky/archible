import typing
import shlex
import dataclasses
import os
import os.path
import stat
import contextlib

from ansible.errors import AnsibleActionFail
from ansible.plugins.action import ActionBase
from ansible.constants import COLOR_CHANGED, COLOR_OK, COLOR_ERROR


SPEC = {
    "dir": dict(type="path", required=False),
    "shells": {
        "type": "list",
        "required": False,
        "default": [],
        "elements": "dict",
        "options": {
            "key": {
                "type": "str",
                "required": True,
            },
            "dir": {
                "type": "str",
                "required": False,
            },
            "shell": {
                "type": "str",
                "required": True,
            },
        },
    },
    "archives": {
        "type": "list",
        "required": False,
        "default": [],
        "elements": "dict",
        "options": {
            "key": {
                "type": "str",
                "required": True,
            },
            "dir": {
                "type": "path",
                "required": False,
            },
            "archive": {
                "type": "list",
                "elements": "str",
                "required": True,
            },
        },
    },
}


@dataclasses.dataclass
class Shell:
    shell: str
    key: str
    dir: str | None = None


@dataclasses.dataclass
class Archive:
    archive: list[str]
    key: str
    dir: str | None = None


@dataclasses.dataclass
class Arguments:
    shells: list[Shell]
    archives: list[Archive]
    dir: str | None = None


class Result(typing.TypedDict):
    failed: typing.NotRequired[bool]
    msg: typing.NotRequired[str]
    changed: typing.NotRequired[bool]


class Persist:
    def __init__(self, persist: str):
        if not os.path.isdir(persist):
            raise AnsibleActionFail("Persist directory must exist.")

        self.persist = persist

        persist_stat = os.stat(self.persist)
        self.mode = persist_stat.st_mode & ~stat.S_ISVTX
        self.owner = persist_stat.st_uid
        self.group = persist_stat.st_gid

    @contextlib.contextmanager
    def _permissions_context(self):
        dropped_exec = self.mode & ~stat.S_IXUSR & ~stat.S_IXGRP & ~stat.S_IXOTH
        old_values = os.getegid(), os.geteuid()
        os.setegid(self.group), os.seteuid(self.owner)
        try:
            yield dropped_exec
        finally:
            [fun(i) for fun, i in zip((os.setegid, os.seteuid), old_values)]

    def write(self, key: str, content: bytes) -> None:
        path = os.path.join(self.persist, key)

        with self._permissions_context() as file_mode:
            parent = os.path.dirname(path)
            if not os.path.isdir(parent):
                os.mkdir(parent, self.mode)
            else:
                os.chmod(parent, self.mode)
                os.chown(parent, self.owner, self.group)

            fd = os.open(
                path, flags=os.O_WRONLY | os.O_CREAT | os.O_TRUNC, mode=file_mode
            )
            with os.fdopen(fd, "wb") as file:
                file.write(content)


class ActionModule(ActionBase):
    TAR_CMD = " ".join(
        (
            "/usr/bin/tar",
            "--numeric-owner",
            "--group=0",
            "--owner=0",
            "--zstd",
            "--create",
            "--to-stdout",
            "--files-from",
            "-",
        )
    )

    def run(self, tmp: None = None, task_vars: dict = None) -> Result:
        args = self._validate_args()
        persist = Persist(self._templar.template(task_vars["policy"]["persist"]))

        for s in args.shells:
            if (content := self._binary_command_wrapped(s, s.shell)) is not None:
                persist.write(s.key, content)

        for a in args.archives:
            find_command = ["/usr/bin/find", "."]
            for it, pattern in enumerate(a.archive):
                if it:
                    find_command.append("-o")
                find_command.extend(("-path", shlex.quote(f"./{pattern}")))

            subcommands = (" ".join(find_command), "cut -c3-", self.TAR_CMD)
            command = "set -o pipefail && " + " | ".join(subcommands)
            if (content := self._binary_command_wrapped(a, command)) is not None:
                persist.write(a.key, content)

        return Result(changed=True)

    def _validate_args(self) -> Arguments:
        _, raw_args = self.validate_argument_spec(
            argument_spec=SPEC,
            required_one_of=[["shells", "archives"]],
        )
        if not any(map(len, (raw_args["shells"], raw_args["archives"]))):
            raise AnsibleActionFail("No-op action.")

        args = Arguments(dir=raw_args["dir"], archives=[], shells=[])
        for subclass, dataclass in {"shells": Shell, "archives": Archive}.items():
            for entry in raw_args[subclass]:
                entry_key = entry["key"]
                if os.path.isabs(entry_key) or len(entry_key.split(os.path.sep)) != 2:
                    raise AnsibleActionFail(
                        "Expected key in format 'collection/item', got {}.".format(
                            entry_key
                        )
                    )

                entry["dir"] = self._validate_args_target_dir(entry["dir"], args.dir)
                getattr(args, subclass).append(dataclass(**entry))

        empty = next((a for a in args.archives if len(a.archive) == 0), None)
        if empty is not None:
            raise AnsibleActionFail(
                "Archive '{}' must define list of items.".format(empty.key),
            )

        return args

    def _validate_args_target_dir(self, directory: str | None, base: str | None) -> str:
        if os.path.isabs(directory or ""):
            return directory

        if base is None:
            raise AnsibleActionFail("Relative dir '{}' without base.".format(directory))
        elif not os.path.isabs(base):
            raise AnsibleActionFail("Non-absolute base directory '{}'.".format(base))
        elif directory is None:
            return base

        return os.path.join(base, directory)

    def _binary_command(self, cmd: str, cwd: str):
        cmd = self._connection._shell.append_command(f"cd {shlex.quote(cwd)}", cmd)
        remote, become = self._get_remote_user(), self.get_become_option("become_user")
        if self._connection.become and (become != remote or not any((become, remote))):
            cmd = self._connection.become.build_become_command(
                cmd, self._connection._shell
            )

        if self._connection.allow_executable:
            cmd = self._connection._shell.append_command(cmd, "sleep 0")
            if executable := self._play_context.executable:
                cmd = executable + " -c " + shlex.quote(cmd)

        return self._connection.exec_command(cmd, sudoable=True)

    def _binary_command_wrapped(
        self, target: Shell | Archive, command: str
    ) -> bytes | None:
        if self._task.check_mode is True:
            self._display.display(
                "ok: ({}) => ({})".format(target.key, command), COLOR_OK
            )
            return None

        rc, stdout, stderr = self._binary_command(command, target.dir)
        if rc != 0:
            self._display.display("failed: ({})".format(target.key), COLOR_ERROR)
            raise AnsibleActionFail(
                message="Non-zero return code.",
                result=dict(rc=rc, dir=target.dir, command=command, stderr=stderr),
            )

        context = target.shell if isinstance(target, Shell) else str(target.archive)
        self._display.display(
            "changed: ({}) => ({}, {})".format(target.key, target.dir, context),
            COLOR_CHANGED,
        )

        return stdout
