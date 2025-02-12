import dataclasses
import typing

from ansible.plugins.action import ActionBase
from ansible.playbook.task import Task
from ansible.constants import COLOR_SKIP


@dataclasses.dataclass
class Arguments:
    url: str
    dest: str
    exclude: list[str]
    creates: str | None = None
    strip: int = None


class Result(typing.TypedDict):
    skipped: typing.NotRequired[bool]
    changed: typing.NotRequired[bool]
    failed: typing.NotRequired[bool]
    msg: typing.NotRequired[str]


class ActionModule(ActionBase):
    def run(self, tmp: None = None, task_vars: dict = None) -> dict[str, typing.Any]:
        args, result = self._build_args(), Result(changed=True)
        if self._task.check_mode:
            return Result()

        if args.creates is not None and self._creates_satisfied(
            task_vars, args.creates
        ):
            self._display.display("exists: ({})".format(args.creates), COLOR_SKIP)
            return Result(skipped=True)

        unpack_result = self._streaming_unpack(task_vars, args)
        if unpack_result.get("failed") is True:
            return unpack_result

        #
        # Probably faster to invoke the module instead of transfering thousand
        #  of lines from `bsdtar v`.
        #
        if args.creates is not None and not self._creates_satisfied(
            task_vars, args.creates
        ):
            return Result(
                failed=True,
                msg="'{}' was not created after the unpacking.".format(args.creates),
            )

        return result

    def _build_args(self) -> Arguments:
        _, raw_args = self.validate_argument_spec(
            argument_spec=dict(
                url=dict(type="str", required=True),
                dest=dict(type="str", required=True),
                exclude=dict(
                    type="list", required=False, elements="str", default=list()
                ),
                creates=dict(type="str", required=False),
                strip=dict(type="int", required=False),
            ),
        )

        return Arguments(**raw_args)

    def _creates_satisfied(self, task_vars: dict, creates: str) -> bool:
        result = self._execute_module(
            module_name="ansible.builtin.stat",
            module_args=dict(path=creates),
            task_vars=task_vars,
        )

        if result.get("failed"):
            return None

        return result["stat"]["exists"]

    def _get_dest_permissions(self, task_vars: typing.Mapping[str, typing.Any]) -> str:
        if self._task._become is True:
            return "root"

        return self._templar.template(task_vars["users"]["user"]["name"])

    def _build_cmdline(self, task_vars: dict, args: Arguments) -> list[str]:
        def quote(string):
            return f'"{string}"'

        permission = self._get_dest_permissions(task_vars)
        cmdline = [
            "set -o pipefail &&",
            "/usr/bin/curl",
            "--silent",
            "--location",
            quote(args.url),
            " | ",
            "/usr/bin/bsdtar",
            "--extract",
            "--same-owner",
            "--group",
            permission,
            "--owner",
            permission,
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
            cmdline.append(quote(rule))

        return cmdline

    def _streaming_unpack(self, task_vars: dir, args: Arguments) -> Result:
        action = self._shared_loader_obj.action_loader.get(
            "ansible.builtin.shell",
            task=Task.load(
                {
                    "ansible.builtin.shell": dict(
                        cmd=" ".join(self._build_cmdline(task_vars, args)),
                        chdir=args.dest,
                    ),
                },
                block=self._task,
                loader=self._loader,
                variable_manager=self._task.get_variable_manager(),
            ),
            connection=self._connection,
            play_context=self._play_context,
            loader=self._loader,
            templar=self._templar,
            shared_loader_obj=self._shared_loader_obj,
        )

        return action.run(task_vars=task_vars)
