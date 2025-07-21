#
# foundation.persist.to - action plugin for transfering persistance files from managed node to control node.
#
# Follow the project README for more information.
#

import shlex
import dataclasses
import os
import os.path
import stat
import contextlib

from ansible.errors import AnsibleActionFail
from ansible.plugins.action import ActionBase
from ansible.constants import COLOR_CHANGED, COLOR_OK

from ansible_collections.foundation.util.types import RawResult, TaskVars
from ansible_collections.foundation.util.dispatch import (
    ansible_binary_command,
)
from ansible_collections.foundation.util.specs import validate_spec


DEFAULTS_SPEC = {
    "base": {
        "type": "path",
        "required": False,
    },
    "persist": {
        "type": "path",
        "required": True,
    },
}

TARGETS_SPEC = {
    "shells": {
        "type": "list",
        "default": [],
        "elements": "dict",
        "options": {
            "dir": {
                "type": "str",
                "required": False,
            },
            "key": {
                "type": "str",
                "required": True,
            },
            "cmd": {
                "type": "str",
                "required": True,
            },
            "stdin": {
                "type": "str",
                "required": False,
            },
        },
    },
    "archives": {
        "type": "list",
        "default": [],
        "elements": "dict",
        "options": {
            "dir": {
                "type": "path",
                "required": False,
            },
            "key": {
                "type": "str",
                "required": True,
            },
            "include": {
                "type": "list",
                "elements": "str",
                "required": True,
            },
        },
    },
}


@dataclasses.dataclass
class Defaults:
    base: str | None
    persist: str


@dataclasses.dataclass
class Shell:
    key: str
    dir: str | None
    cmd: str
    stdin: str | None


@dataclasses.dataclass
class Archive:
    key: str
    dir: str | None
    include: list[str]


@dataclasses.dataclass
class Targets:
    shells: list[Shell]
    archives: list[Archive]


#
# Dedicated class for persistence filesystem access.
#
class Persist:
    def __init__(self, persist: str):
        if not os.path.isdir(persist):
            raise AnsibleActionFail("Persist directory must exist")

        self.persist = persist

        #
        # Check current persistence directory permissions to ensure the desired state, 
        # even when Ansible runs as root (e.g., via connection plugins).
        #
        persist_stat = os.stat(self.persist)
        #
        # Define a mode for directories, omitting the sticky bit if set.
        #
        self.mode = persist_stat.st_mode & ~stat.S_ISVTX
        self.owner = persist_stat.st_uid
        self.group = persist_stat.st_gid

        self.changed = False

    #
    # Temporarily change effective UID and GID, so that created files wi
    #
    @contextlib.contextmanager
    def _permissions_context(self):
        egid, euid = os.getegid(), os.geteuid()
        try:
            os.setegid(self.group), os.seteuid(self.owner)

            #
            # Return file mode without execution bits, as persistence items are plain files.
            #
            yield self.mode & ~stat.S_IXUSR & ~stat.S_IXGRP & ~stat.S_IXOTH
        finally:
            os.setegid(egid)
            os.seteuid(euid)

    def write(self, key: str, content: bytes) -> None:
        path = os.path.join(self.persist, key)

        with self._permissions_context() as file_mode:
            parent = os.path.dirname(path)
            #
            # Ensure appropriate directory permissions are set.
            #
            if not os.path.isdir(parent):
                os.mkdir(parent, self.mode)
            else:
                os.chmod(parent, self.mode)
                os.chown(parent, self.owner, self.group)

            #
            # Manually open file with specified permissions to avoid chmod errors and possible cleanup of intermediate
            #  files.
            #
            fd = os.open(
                path=path,
                flags=os.O_WRONLY | os.O_CREAT | os.O_TRUNC,
                mode=file_mode,
            )
            with os.fdopen(fd, "wb") as file:
                file.write(content)

            self.changed = True


class ActionModule(ActionBase):
    TAR_CMD = " ".join(
        (
            "/usr/bin/tar",
            "--no-recursion",
            "--numeric-owner",
            "--group=0",
            "--owner=0",
            "--gzip",
            "--create",
            "--files-from",
            "-",
        )
    )

    def run(self, tmp: None = None, task_vars: TaskVars = None) -> RawResult:
        defaults, targets = self._validate_inputs()
        persist = Persist(defaults.persist)

        self._process_shells(targets, persist)
        self._process_archives(targets, persist)

        return RawResult(changed=persist.changed)

    def _validate_inputs(self) -> tuple[Defaults, Targets]:
        defaults = Defaults(**self.validate_argument_spec(DEFAULTS_SPEC)[1])
        if defaults.base is not None and not os.path.isabs(defaults.base):
            raise AnsibleActionFail(f"Non-absolute base directory '{defaults.base}'")

        raw_vars = validate_spec(TARGETS_SPEC, self._templar.template(self._task.vars), ["shells", "archives"])
        if not any(map(len, (raw_vars["shells"], raw_vars["archives"]))):
            raise AnsibleActionFail("No-op action")

        targets = Targets(archives=[], shells=[])
        for subclass, dataclass in {"shells": Shell, "archives": Archive}.items():
            for entry in raw_vars[subclass]:
                entry_key = entry["key"]
                if os.path.isabs(entry_key) or len(entry_key.split(os.path.sep)) != 2:
                    raise AnsibleActionFail("Expected key in format 'collection/item', got {}.".format(entry_key))

                #
                # Handle target-level overrides and fallback.
                #
                entry["dir"] = self._validate_args_target_dir(
                    entry["dir"],
                    defaults.base,
                )
                getattr(targets, subclass).append(dataclass(**entry))

        #
        # Disallow empty item lists; use '*' to archive all files.
        #
        empty = next((True for a in targets.archives if len(a.include) == 0), None)
        if empty is not None:
            raise AnsibleActionFail(
                "Archive '{}' must define list of items".format(empty.key),
            )

        return defaults, targets

    def _validate_args_target_dir(self, directory: str | None, base: str | None) -> str:
        if directory is not None:
            if os.path.isabs(directory):
                return directory
            elif not directory.startswith("./"):
                raise AnsibleActionFail(f"Relative dir '{directory}' must have './' prefix")

        if base is None:
            raise AnsibleActionFail("Global base directory or absolute local must be set")
        elif directory is None:
            return base

        return os.path.normpath(os.path.join(base, directory))

    def _process_shells(self, targets: Targets, persist: Persist) -> None:
        for shell in targets.shells:
            content = self._binary_command_wrapped(shell, shell.cmd, shell.stdin.encode() if shell.stdin else None)
            if content is not None:
                persist.write(shell.key, content)

    def _process_archives(self, targets: Targets, persist: Persist) -> None:
        for archive in targets.archives:
            find_command = ["/usr/bin/find", "."]
            for it, pattern in enumerate(archive.include):
                if it:
                    find_command.append("-o")

                find_command.extend(("-path", shlex.quote(f"./{pattern}")))

            subcommands = (" ".join(find_command), "cut -c3-", self.TAR_CMD, "cat")
            content = self._binary_command_wrapped(archive, "set -o pipefail && " + " | ".join(subcommands))
            if content is not None:
                persist.write(archive.key, content)

    def _binary_command_wrapped(
        self, target: Shell | Archive, command: str, stdin: bytes | None = None
    ) -> bytes | None:
        context = "({}:{}) => ({}, {})".format(
            type(target).__name__.lower(),
            target.key,
            target.dir,
            command if isinstance(target, Shell) else target.include,
        )
        if self._task.check_mode is True:
            self._display.display(f"ok: {context}", COLOR_OK)
            return None

        rc, stdout, stderr = ansible_binary_command(self, command, target.dir, stdin)
        if rc != 0:
            raise AnsibleActionFail(
                message="Non-zero return code",
                result=dict(rc=rc, dir=target.dir, command=command, stderr=stderr),
            )
        else:
            self._display.display(f"changed: {context}", COLOR_CHANGED)

        return stdout
