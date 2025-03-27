import typing

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
            key = "default"
            if choice.get("link") is None:
                key = choice.get(layout, key)

            if key not in choice:
                raise AnsibleError("Invalid layout choice '{}'.".format(choice))

            return_values.append(choice[key])

        return return_values
