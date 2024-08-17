# -*- coding: utf-8 -*-
# Based on chroot.py (community.general.chroot):
# (c) 2012, Michael DeHaan <michael.dehaan@gmail.com>
# (c) 2013, Maykel Moya <mmoya@speedyrails.com>
# (c) 2015, Toshio Kuratomi <tkuratomi@ansible.com>
# Copyright (c) 2017 Ansible Project
# GNU General Public License v3.0+ (see LICENSES/GPL-3.0-or-later.txt or https://www.gnu.org/licenses/gpl-3.0.txt)
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import (absolute_import, division, print_function)
__metaclass__ = type

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


from ansible.errors import AnsibleError
from ansible.module_utils.common.text.converters import to_bytes, to_native

from ansible.utils.display import Display
from ansible.utils.shlex import shlex_split

from ansible_collections.community.general.plugins.connection.chroot import Connection as ChrootConnection


display = Display()


class Connection(ChrootConnection):
    """ Systemd-nspawn (machinectl-less, i.e. stateless) connections """

    #
    # Unlike chroot, we do have an option to select a user (via --user)
    #
    default_user = None

    def __init__(self, play_context, new_stdin, *args, **kwargs):
        super(ChrootConnection, self).__init__(play_context, new_stdin, *args, **kwargs)

    def _connect(self):
        """ connect to the container.
        In reality, since there is no preparation required, just construct argument list
        for future use.
        """
        if os.geteuid() != 0:
            raise AnsibleError("nspawn connection requires running ansible as root.")

        #
        # self.chroot is required to be set for the chroot plugin
        #
        self.chroot = self.nspawn_root = self.get_option("nspawn_root")

        user = self.get_option("nspawn_user")
        #
        # To be Python 2 compatible, no star (*) unpacking is used here
        #
        self.nspawn_args = \
            [self.get_option("nspawn_exe")] + \
            shlex_split(self.get_option("nspawn_args")) + \
            (["--user=%s" % user] if user is not None else []) + \
            ["--directory=%s" % self.nspawn_root] + \
            ["--"]
        display.vvv("NSPAWN ARGS %s" % self.nspawn_args, host=self.nspawn_root)

        super(ChrootConnection, self)._connect()
        if not self._connected:
            display.vvv("NSPAWN CONNECTION", host=self.nspawn_root)
            self._connected = True

    #
    # This code is mostly taken from the ansible.plugins.connection.local
    # with the exception that non-bootable containers do not use sudo
    # cache, therefore only login may occur, which simplifies the code.
    #
    def _nspawn_become(self, in_fd, out_fd):
        become_output = b''
        while not self.become.check_password_prompt(become_output):
            select.select([in_fd], [], [], self._play_context.timeout)
            chunk = in_fd.read()
            if not chunk:
                raise AnsibleError(
                    'unexpected empty chunk for privilege escalation output::\n' + to_native(become_output))

            become_output += chunk
            display.vvv("NSPAWN BECOME CHUNK %s" % become_output, host=self.nspawn_root)

        become_pass = self.become.get_option('become_pass', playcontext=self._play_context)
        out_fd.write(to_bytes(become_pass, errors='surrogate_or_strict') + b'\n')

    #
    # Slightly modifed version that additionally passes sudoable into _buffered_exec_command
    # This would solve a problem when other executions (such as put_file via dd) is interpreted
    # as sudo command. 
    #
    def exec_command(self, cmd, in_data=None, sudoable=False):
        """ run a command on the chroot """
        super(ChrootConnection, self).exec_command(cmd, in_data=in_data, sudoable=sudoable)
        
        display.vvv("NSPAWN EXEC SUDOABLE %d COMMAND %s" % (sudoable, cmd), host=self.nspawn_root)
        p = self._buffered_exec_command(cmd, sudoable=sudoable)

        stdout, stderr = p.communicate(in_data)
        return p.returncode, stdout, stderr

    def _buffered_exec_command(self, cmd, stdin=subprocess.PIPE, sudoable=False):
        """ run a command on the systemd-nspawn container.
        Most of the logic is already implemented in community.general.chroot, 
        except execution command and become.
        """
        #
        # Using shlex_split to skip one level of nesting /bin/sh -c
        #
        cmdline = [
            to_bytes(i, errors='surrogate_or_strict')
            for i in self.nspawn_args + shlex_split(cmd)
        ]

        display.vvv("NSPAWN BUFFERED EXEC %s" % cmdline, host=self.nspawn_root)
        p = subprocess.Popen(
            cmdline, shell=False,
            stdin=stdin, stdout=subprocess.PIPE, stderr=subprocess.PIPE
        )
        
        if sudoable and self.become and self.become.expect_prompt():
            try:
                fcntl.fcntl(p.stderr, fcntl.F_SETFL, fcntl.fcntl(p.stderr, fcntl.F_GETFL) | os.O_NONBLOCK)
                self._nspawn_become(p.stderr, p.stdin)
            finally:
                fcntl.fcntl(p.stderr, fcntl.F_SETFL, fcntl.fcntl(p.stderr, fcntl.F_GETFL) | ~os.O_NONBLOCK)

        return p
