#
# foundation.files.net_archive - download and unpack network archive with creation guards.
#
# Follow the project README for more information.
#

import dataclasses
import os.path
import shlex

from ansible.plugins.action import ActionBase
from ansible.errors import AnsibleActionFail
from ansible.constants import COLOR_SKIP

from ansible_collections.foundation.util.types import RawResult, TaskVars
from ansible_collections.foundation.util.dispatch import ansible_dispatch


@dataclasses.dataclass
class Arguments:
    url: str
    dest: str
    exclude: list[str]
    creates: list[str]
    strip: int
    perms: tuple[str, str]


class ActionModule(ActionBase):
    def run(self, tmp: None = None, task_vars: TaskVars = None) -> RawResult:
        args, result = self._build_args(task_vars), RawResult(changed=True)

        if self._creates_satisfied(args, task_vars):
            self._display.display("exists: ({})".format(args.creates), COLOR_SKIP)
            return RawResult(skipped=True)
        elif self._task.check_mode:
            return RawResult()

        unpack_result = ansible_dispatch(
            self,
            "ansible.builtin.shell",
            dict(
                cmd=" ".join(self._build_cmdline(args)),
                chdir=args.dest,
            ),
            task_vars,
        )
        if unpack_result.get("failed") is True:
            return unpack_result

        #
        # Probably faster to invoke the module instead of transfering thousand of lines from `bsdtar v`.
        #
        if not self._creates_satisfied(args, task_vars):
            raise AnsibleActionFail("'{}' was not created after the unpacking".format(args.creates))

        return result

    def _build_args(self, task_vars: TaskVars) -> Arguments:
        _, raw_args = self.validate_argument_spec(
            argument_spec=dict(
                url=dict(type="str", required=True),
                dest=dict(type="path", required=True),
                exclude=dict(
                    type="list",
                    elements="str",
                    default=list(),
                ),
                creates=dict(type="list", elements="path", default=list()),
                strip=dict(type="int", default=0),
                perms=dict(type="str", required=True),
            ),
        )

        group, split, owner = raw_args["perms"].partition(":")
        if not split:
            raise AnsibleActionFail("Permission must be set (owner:group)")
        else:
            raw_args["perms"] = (group, owner)

        return Arguments(**raw_args)

    def _creates_satisfied(self, args: Arguments, task_vars: TaskVars) -> bool:
        for path in args.creates:
            abs_path = path if os.path.isabs(path) else os.path.join(args.dest, path)
            result = self._execute_module(
                module_name="ansible.builtin.stat",
                module_args=dict(path=abs_path),
                task_vars=task_vars,
            )
            if result.get("failed") is True or not result["stat"]["exists"]:
                return False

        return True

    def _build_cmdline(self, args: Arguments) -> list[str]:
        cmdline = [
            "set -o pipefail &&",
            "/usr/bin/curl",
            "--silent",
            "--location",
            shlex.quote(args.url),
            " | ",
            "/usr/bin/bsdtar",
            "--extract",
            "--same-owner",
            "--owner", args.perms[0],
            "--group", args.perms[1],
            "--preserve-permissions",
            "--no-acls",
            "--no-mac-metadata",
            "--no-xattrs",
            "--file",
            "-",
        ]
        if args.strip:
            cmdline.append(f"--strip-components={args.strip}")

        for rule in args.exclude:
            cmdline.append("--exclude")
            cmdline.append(shlex.quote(rule))

        return cmdline
