import shlex

from ansible.plugins.action import ActionBase
from ansible.playbook.task import Task

from ansible_collections.foundation.util.types import RawResult, TaskVars


def ansible_dispatch(ctx: ActionBase, name: str, payload: dict, task_vars: TaskVars) -> RawResult:
    if ctx._task.check_mode is True:
        return RawResult()

    action = ctx._shared_loader_obj.action_loader.get(
        name,
        task=Task.load(
            {name: payload},
            block=ctx._task,
            loader=ctx._loader,
            variable_manager=ctx._task.get_variable_manager(),
        ),
        connection=ctx._connection,
        play_context=ctx._play_context,
        loader=ctx._loader,
        templar=ctx._templar,
        shared_loader_obj=ctx._shared_loader_obj,
    )
    if action is None:
        return ctx._execute_module(name, payload, task_vars=task_vars)

    return action.run(task_vars=task_vars)


def ansible_binary_command(
    ctx: ActionBase,
    cmd: str,
    cwd: str,
    stdin: bytes | None = None,
) -> tuple[int, bytes, bytes]:
    cmd = ctx._connection._shell.append_command(f"cd {shlex.quote(cwd)}", cmd)

    remote, become = ctx._get_remote_user(), ctx.get_become_option("become_user")
    if ctx._connection.become and (become != remote or not any((become, remote))):
        cmd = ctx._connection.become.build_become_command(cmd, ctx._connection._shell)

    if ctx._connection.allow_executable:
        cmd = ctx._connection._shell.append_command(cmd, "sleep 0")
        if executable := ctx._play_context.executable:
            cmd = executable + " -c " + shlex.quote(cmd)

    return ctx._connection.exec_command(cmd, in_data=stdin, sudoable=True)
