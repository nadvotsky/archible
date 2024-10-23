# -*- coding: utf-8 -*-
# Based on chroot.py (community.general.chroot):
# (c) 2012, Michael DeHaan <michael.dehaan@gmail.com>
# (c) 2013, Maykel Moya <mmoya@speedyrails.com>
# (c) 2015, Toshio Kuratomi <tkuratomi@ansible.com>
# Copyright (c) 2017 Ansible Project
# GNU General Public License v3.0+ (see LICENSES/GPL-3.0-or-later.txt or https://www.gnu.org/licenses/gpl-3.0.txt)
# SPDX-License-Identifier: GPL-3.0-or-later

DOCUMENTATION = '''
    name: nspawn
    short_description: Interact with systemd-nspawn container.
    description:
      - Run commands or put/fetch files to an systemd-nspawn container on the Ansible controller.
    options:
      nspawn_root:
        description:
          - The path to the root directory to start container from.
        vars:
          - name: ansible_nspawn_root
        type: path
        default: /mnt
      nspawn_exe:
        description:
          - User specified executable binary for systemd-nspawn.
        vars:
          - name: ansible_nspawn_exe
        type: path
        default: /usr/bin/systemd-nspawn
      nspawn_user:
        description:
          - User specified user that is passed via --user to the systemd-nspawn.
        vars:
          - name: ansible_nspawn_user
        required: false
      nspawn_args:
        description:
            - Additional arguments passed to the systemd-nspawn. 
            - Note that there is no need to specify --directory or --user, as they are controlled by
              V(nspawn_root) and V(nspawn_user).
        vars:
          - name: ansible_nspawn_args
        type: str
        default: --quiet --as-pid2 --pipe
'''

import os
import subprocess
import fcntl
import select
import functools


from ansible.errors import AnsibleError
from ansible.module_utils.common.text.converters import to_bytes, to_native

from ansible.utils.display import Display
from ansible.utils.shlex import shlex_split

from ansible_collections.community.general.plugins.connection.chroot import Connection as ChrootConnection


class Connection(ChrootConnection):
    """ Systemd-nspawn (machinectl-less, i.e. stateless) connections """

    #
    # Unlike the chroot plugin, we do have an option to select a user (via --user)
    #
    default_user = None

    #
    # A constructor that only calls corresponding base constructor of class hierarchy.
    #
    # The actual initializion of desired variables and stuff is implemented
    #  in the `_connect` method as other plugins usually do.
    #
    # Note the usage of super():
    #  it calls not the direct base class ChrootConnection,
    #  but ConnectionBase instead
    #
    # The purpose of this is to omit useless operations (and also errors) that
    #  are not related to the nspawn functional.
    #
    def __init__(self, *args, **kwargs):
        super(ChrootConnection, self).__init__(*args, **kwargs)

    def _connect(self):
        if os.geteuid() != 0:
            raise AnsibleError("nspawn connection requires running ansible as root.")

        #
        # `self.chroot` is required to be set for the chroot plugin
        #
        self.chroot = self._nspawn_root = self.get_option("nspawn_root")
        self._nspawn_log = functools.partial(Display().vvv, host=self._nspawn_root) 

        user = self.get_option("nspawn_user")
        self._nspawn_args = [
            self.get_option("nspawn_exe"),
            *shlex_split(self.get_option("nspawn_args")),
            *([f"--user={user}"] if user is not None else []),
            f"--directory={self._nspawn_root}", 
            "--",
        ]
        self._nspawn_log(f"NSPAWN ARGS {self._nspawn_args}")

        #
        # Calling `ConnectionBase` because `ChrootConnection`
        # constructs unnecessary arguments list and prints some messages.
        #
        super(ChrootConnection, self)._connect()
        if not self._connected:
            self._nspawn_log("NSPAWN NEW CONNECTION")
            self._connected = True

    #
    # This code is mostly taken from the ansible.plugins.connection.local
    #  with the exception that non-bootable containers do not use sudo
    #  cache, therefore only login may occur, which simplifies the code.
    #
    def _nspawn_become(self, in_fd, out_fd):
        become_output = b''
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
    # This would solve a problem when other executions (such as `put_file` which uses `dd`) are
    # interpreted as sudo command. 
    #
    def exec_command(self, cmd, in_data=None, sudoable=False):
        #
        # Bypassing `ChrootConnection.exec_command` prior to `ConnectionBase.exec_command`.
        #
        super(ChrootConnection, self).exec_command(cmd, in_data=in_data, sudoable=sudoable)

        self._nspawn_log(f"NSPAWN EXEC SUDOABLE {sudoable} COMMAND :: {cmd}")
        p = self._buffered_exec_command(cmd, sudoable=sudoable)

        stdout, stderr = p.communicate(in_data)
        return p.returncode, stdout, stderr

    #
    # Run a command on the systemd-nspawn container.
    #
    def _buffered_exec_command(self, cmd, stdin=subprocess.PIPE, sudoable=False):
        #
        # Using `shlex_split` to skip one level of nesting /bin/sh -c
        #
        cmdline = [
            to_bytes(i, errors='surrogate_or_strict')
            for i in self._nspawn_args + shlex_split(cmd)
        ]
        p = subprocess.Popen(
            cmdline, shell=False,
            stdin=stdin, stdout=subprocess.PIPE, stderr=subprocess.PIPE
        )

        if sudoable and self.become and self.become.expect_prompt():
            flags = fcntl.fcntl(p.stderr, fcntl.F_GETFL)
            try:
                fcntl.fcntl(p.stderr, fcntl.F_SETFL, flags | os.O_NONBLOCK)
                self._nspawn_become(p.stderr, p.stdin)
            finally:
                fcntl.fcntl(p.stderr, fcntl.F_SETFL, flags | ~os.O_NONBLOCK)

        return p
