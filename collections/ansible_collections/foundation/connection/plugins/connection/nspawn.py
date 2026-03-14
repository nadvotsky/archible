#
# foundation.connection.nspawn - systemd-nspawn connection plugin for Ansible.
#
# Based on chroot.py (community.general.chroot).
# Refer to https://github.com/ansible-collections/community.general/blob/main/plugins/connection/chroot.py for details.
#

import os
import subprocess
import fcntl
import select
import functools
import shutil

from ansible.errors import AnsibleError
from ansible.module_utils.common.text.converters import to_bytes, to_native

from ansible.utils.display import Display
from ansible.utils.shlex import shlex_split
from ansible.module_utils.six.moves import shlex_quote

from ansible.plugins.connection import ConnectionBase, BUFSIZE


DOCUMENTATION = """
---
name: foundation.connection.nspawn
short_description: Interact with systemd-nspawn container.
description:
    - Run commands or put/fetch files to a systemd-nspawn container on the Ansible controller.
options:
    nspawn_root:
        type: path
        default: /mnt
        description:
            - The path to the root directory to start container from.
        vars:
            - name: foundation_nspawn_root
    nspawn_exe:
        type: path
        default: /usr/bin/systemd-nspawn
        description:
            - User specified executable binary for systemd-nspawn.
        vars:
            - name: foundation_nspawn_exe
    nspawn_args:
        type: str
        default: --quiet --as-pid2 --pipe
        description:
            - Additional arguments passed to the systemd-nspawn.
            - Note that there is no need to specify --directory or --user, as they are controlled by V(nspawn_root) and
              V(ansible_user).
        vars:
            - name: foundation_nspawn_args
"""

EXAMPLES = """
# Standard host declaration.
main:
    hosts:
        main_prelude:
            ansible_user: user
            ansible_become_password: password
            ansible_connection: foundation.connection.nspawn
            foundation_nspawn_root: /mnt
            foundation_nspawn_args: >-
                --quiet --register=no --as-pid2 --pipe
                --hostname=example --machine=example
                --resolv-conf=bind-host --timezone=off --link-journal=no
"""


class Connection(ConnectionBase):
    """Systemd-nspawn (machinectl-less, i.e. stateless) connections"""

    transport = "foundation.connection.nspawn"
    has_pipelining = True
    has_tty = False

    #
    # Unlike the chroot plugin, we do have an option to select a user (via --user)
    #
    default_user = None

    #
    # A constructor that only calls corresponding base constructor of class hierarchy.
    #
    # The actual initialization of desired variables and stuff is implemented in the `_connect` method.
    #
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

    def _connect(self):
        if os.geteuid() != 0:
            raise AnsibleError("nspawn connection requires running ansible as root")

        self._nspawn_root = self.get_option("nspawn_root")
        self._nspawn_log = functools.partial(Display().vvv, host=self._nspawn_root)

        self._nspawn_args = [
            self.get_option("nspawn_exe"),
            *shlex_split(self.get_option("nspawn_args")),
            f"--directory={self._nspawn_root}",
        ]
        if self._play_context.remote_user:
            self._nspawn_args.append("--user={}".format(self._play_context.remote_user))

        self._nspawn_args.append("--")
        self._nspawn_log(f"NSPAWN: ARGS {self._nspawn_args}")

        #
        # Calling `ConnectionBase` because `ChrootConnection` constructs unnecessary arguments and prints some messages.
        #
        super()._connect()
        if not self._connected:
            self._nspawn_log("NSPAWN: NEW CONTAINER")
            self._connected = True

    #
    # This code is mostly taken from the `ansible.plugins.connection.local` with the exception that non-bootable
    #  containers do not use sudo cache, therefore only login may occur, which simplifies the code.
    #
    def _nspawn_become(self, in_fd, out_fd):
        become_output = b""
        while not self.become.check_password_prompt(become_output):
            select.select([in_fd], [], [], self._play_context.timeout)
            chunk = in_fd.read()
            if not chunk:
                raise AnsibleError(
                    f"unexpected empty chunk for privilege escalation output :: {to_native(become_output)}\n"
                )

            become_output += chunk
            self._nspawn_log(f"NSPAWN BECOME CHUNK :: {become_output}")

        become_pass = self.become.get_option("become_pass", playcontext=self._play_context)
        out_fd.write(to_bytes(become_pass, errors="surrogate_or_strict") + b"\n")

    #
    # Slightly modifed version that additionally passes `sudoable` into the `_buffered_exec_command`.
    # This would solve a problem when other commands (such as `put_file` which uses `dd`) are interpreted as sudo command.
    #
    def exec_command(self, cmd, in_data=None, sudoable=False):
        super().exec_command(cmd, in_data=in_data, sudoable=sudoable)

        self._nspawn_log(f"NSPAWN: EXEC SUDOABLE {sudoable} COMMAND :: {cmd}")
        p = self._buffered_exec_command(cmd, sudoable=sudoable)

        stdout, stderr = p.communicate(in_data)
        return p.returncode, stdout, stderr

    #
    # Run a command on the systemd-nspawn container.
    #
    def _buffered_exec_command(self, cmd, stdin=subprocess.PIPE, sudoable=False):
        #
        # Using `shlex_split` to skip one level of nesting `/bin/sh -c`.
        #
        cmdline = [to_bytes(i, errors="surrogate_or_strict") for i in self._nspawn_args + shlex_split(cmd)]
        p = subprocess.Popen(
            cmdline,
            shell=False,
            stdin=stdin,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )

        if sudoable and self.become and self.become.expect_prompt():
            flags = fcntl.fcntl(p.stderr, fcntl.F_GETFL)
            try:
                fcntl.fcntl(p.stderr, fcntl.F_SETFL, flags | os.O_NONBLOCK)
                self._nspawn_become(p.stderr, p.stdin)
            finally:
                fcntl.fcntl(p.stderr, fcntl.F_SETFL, flags | ~os.O_NONBLOCK)

        return p

    def put_file(self, in_path, out_path):
        super().put_file(in_path, out_path)
        self._nspawn_log(f"NSPAWN: PUT {in_path} => {out_path}")

        escaped_out = shlex_quote(out_path)
        with open(to_bytes(in_path, errors="surrogate_or_strict"), "rb") as in_file:
            count = " count=0" if not os.fstat(in_file.fileno()).st_size else ""
            p = self._buffered_exec_command(f'dd of={escaped_out} bs={BUFSIZE}{count}', stdin=in_file)

            _, stderr = p.communicate()
            if p.returncode != 0:
                raise AnsibleError(f"failed to transfer file {in_path} to {out_path}: {stderr}")

    def fetch_file(self, in_path, out_path):
        super().fetch_file(in_path, out_path)
        self._nspawn_log(f"NSPAWN: FETCH {in_path} => {out_path}")

        p = self._buffered_exec_command(f"dd if={shlex_quote(in_path)} bs={BUFSIZE}")
        with open(to_bytes(out_path, errors="surrogate_or_strict"), "wb+") as out_file:
            shutil.copyfileobj(p.stdout, out_file)

            _, stderr = p.communicate()
            if p.returncode != 0:
                raise AnsibleError(f"failed to transfer file {in_path} to {out_path}: {stderr}")

    def close(self):
        super().close()
        self._connected = False
