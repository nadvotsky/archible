import functools
import pathlib

from ansible.plugins.lookup import LookupBase


class LookupModule(LookupBase):
    def run(self, args: list, variables: dict = None, **kwargs) -> list[str]:
        self.set_options(var_options=variables, direct=kwargs)

        home, dirs = pathlib.Path(args[0]), args[1]

        def each_parent(a, b):
            joint = a / b
            return_values.append(
                dict(dir=home.joinpath(joint).resolve().__str__())
            )

            return joint

        return_values = []
        for directory in map(pathlib.Path, dirs):
            functools.reduce(
                each_parent,
                directory.relative_to(home).parts,
                pathlib.Path()
            )

        return return_values
