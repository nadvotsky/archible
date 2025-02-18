import typing
import operator

from ansible.errors import AnsibleError
from ansible.plugins.lookup import LookupBase


class Choice(typing.TypedDict):
    default: typing.NotRequired[str]

    dot: typing.NotRequired[str]
    xdg: typing.NotRequired[str]


class LookupModule(LookupBase):
    def run(self, choices: list[Choice], variables: dict = None, **kwargs) -> list[str]:
        self.set_options(var_options=variables, direct=kwargs)

        layout = self._templar.template(variables["users"]["user"]["layout"])
        if layout not in ("xdg", "dot"):
            raise AnsibleError("'users.user.layout' must be either 'xdg' or 'dot'.")

        return_values = []
        for choice in choices:
            keys = tuple(filter(lambda k: k in choice, ("xdg", "dot", "default")))
            if len(keys) == 0:
                raise AnsibleError("Invalid layout choice '{}'.".format(choice))

            return_values.extend((choice[key] for key in keys))

        return list(set(return_values))
