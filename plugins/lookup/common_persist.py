import pathlib

from ansible.errors import AnsibleError
from ansible.plugins.lookup import LookupBase


class LookupModule(LookupBase):
    def run(self, keys, variables: dict = None, **kwargs) -> list[bool]:
        self.set_options(var_options=variables, direct=kwargs)

        persist = pathlib.Path(self._templar.template(variables["policy"]["persist"]))
        if not persist.is_dir():
            raise AnsibleError(
                "Persist directory '{}' must exist.".format(str(persist))
            )

        return_values = []
        for key in keys:
            key_path = persist.joinpath(key)
            if len(key_path.relative_to(persist).parts) != 2:
                raise AnsibleError(
                    "Expected exactly two components in persistance key '{}'.".format(
                        key
                    ),
                )

            return_values.append(key_path.is_file())

        return return_values
