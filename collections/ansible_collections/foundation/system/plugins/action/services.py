#
# foundation.system.packages - manage system services with declarative syntax and headless support.
#
# Follow the project README for more information.
#

import typing

import dataclasses
import itertools

from ansible.errors import AnsibleActionFail
from ansible.plugins.action import ActionBase
from ansible.constants import COLOR_ERROR, COLOR_CHANGED, COLOR_OK

from ansible_collections.foundation.util.types import RawResult, TaskVars
from ansible_collections.foundation.util.specs import validate_spec


ARGS_SPEC = {
    "headless": {
        "type": "bool",
        "required": True,
    },
}

VARS_SPEC = {
    "state": {
        "type": "dict",
        "required": True,
        "options": {
            "mask": dict(type="bool", required=False),
            "unmask": dict(type="bool", required=False),
            "enable": dict(type="bool", required=False),
            "disable": dict(type="bool", required=False),
            "start": dict(type="bool", required=False),
            "stop": dict(type="bool", required=False),
            "reload": dict(type="bool", required=False),
        },
    },
    "units": dict(type="list", elements="str", required=True),
}


class Arguments:
    def __init__(self, headless: bool):
        self.headless = headless


#
# Because flag implications are dynamic, it's unnecessary to adopt the full VARS_SPEC.  Using a dictionary is actually
#  more beneficial.
#
type State = typing.Mapping[str, bool | None]


@dataclasses.dataclass
class DomainState:
    #
    # Defines intermediate meta states with corresponding positive and negative actions.
    #
    META: typing.ClassVar[dict[str, tuple[str, str]]] = {
        "unmasking": ("unmask", "mask"),
        "autostart": ("enable", "disable"),
        "runtime": ("start", "stop"),
    }
    #
    # Positive states also imply the associated meta state.
    #
    IMPLIES: typing.ClassVar[dict[str, str]] = {
        "unmasking": "runtime",
        "autostart": "runtime",
    }

    unmasking: bool | None = None
    autostart: bool | None = None
    runtime: bool | None = None
    reload: bool | None = None

    def _process_meta_group(self, domain_attr: str, state: State, state_attrs: tuple[str, str]):
        domain_val = None

        #
        # Set domain attribute by procssing all possible states.
        #
        for attr in state_attrs:
            value = state[attr]
            opposite = next((state for state in state_attrs if state != attr))

            if value is None:
                continue
            elif value is False:
                #
                # State flags are truthy booleans only, do no allow inverting.
                #
                raise AnsibleActionFail("'{}' flag cannot be false, use {} instead.".format(attr, opposite))
            elif domain_val is not None:
                raise AnsibleActionFail(
                    "'{}' is mutually exclusive with '{}'.".format(
                        attr,
                        opposite,
                    )
                )

            domain_val = state_attrs.index(attr) == 0

        #
        # Skip if this attribute is not defined.
        #
        if domain_val is None:
            return

        setattr(self, domain_attr, domain_val)
        if domain_attr in self.IMPLIES:
            setattr(self, self.IMPLIES[domain_attr], domain_val)

    @classmethod
    def from_state(cls, state: State) -> "DomainState":
        all_undefined = all((state[key] is None for key in itertools.chain.from_iterable(cls.META.values())))
        if all_undefined and not state["reload"]:
            raise AnsibleActionFail("State is no-op.")

        #
        # Reload is a special state that does not proper meta states parsing.
        #
        domain = DomainState(reload=state["reload"])
        for domain_attr, state_attrs in cls.META.items():
            domain._process_meta_group(domain_attr, state, state_attrs)

        return domain


class SystemdModuleArgs(typing.TypedDict):
    name: str
    daemon_reload: bool
    daemon_reexec: bool
    enabled: bool
    masked: bool
    scope: typing.Literal["system", "user", "global"]
    state: typing.Literal["reloaded", "restarted", "started", "stopped"]


class ActionModule(ActionBase):
    def run(self, tmp: None = None, task_vars: TaskVars = None) -> RawResult:
        args: Arguments = Arguments(**self.validate_argument_spec(argument_spec=ARGS_SPEC)[1])
        units, domain_state = self._consume_vars()

        #
        # Headless setups lack connection to the systemd socket, however still capable of managing services state.
        #
        if args.headless is True:
            self._task.environment.append(dict(SYSTEMD_OFFLINE="1", SYSTEMD_IN_CHROOT="1"))

        module_args = SystemdModuleArgs(
            scope="system" if self._task._become is True else "user",
        )
        try:
            #
            # Premature reload, if requested.
            #
            if domain_state.reload is True:
                self._run_systemd_module(task_vars, module_args | dict(daemon_reload=domain_state.reload))

            self._handle_units(task_vars, domain_state, units, module_args)

        except AnsibleActionFail as fail:
            return fail.result

        return RawResult()

    def _consume_vars(self) -> tuple[list[str], DomainState]:
        variables = validate_spec(VARS_SPEC, self._templar.template(self._task.vars))

        return variables["units"], DomainState.from_state(variables["state"])

    def _handle_units(
        self,
        task_vars: dict,
        domain_state: DomainState,
        services: list[str],
        module_args: SystemdModuleArgs,
    ) -> None:
        for service in services:
            local_module_args: SystemdModuleArgs = module_args | dict(name=service)
            if domain_state.autostart is not None:
                local_module_args["enabled"] = domain_state.autostart
            if domain_state.unmasking is not None:
                local_module_args["masked"] = not domain_state.unmasking
            if domain_state.runtime is not None:
                local_module_args["state"] = "restarted" if domain_state.runtime is True else "stopped"

            self._run_systemd_module(task_vars, local_module_args)

    def _run_systemd_module(self, task_vars: dict, module_args: SystemdModuleArgs) -> None:
        details = ", ".join([f"{k}={v}" for k, v in module_args.items()])
        if self._task.check_mode:
            result = {}
        else:
            result = self._execute_module(
                module_name="ansible.builtin.systemd_service",
                module_args=module_args,
                task_vars=task_vars,
            )

        match result:
            case {"failed": True}:
                tag, color = "failed", COLOR_ERROR
            case {"changed": True}:
                tag, color = "changed", COLOR_CHANGED
            case _:
                tag, color = "ok", COLOR_OK

        self._display.display(f"{tag}: ({details})", color)

        if result.get("failed") is True:
            raise AnsibleActionFail(message=result.get("msg"), result=result)
