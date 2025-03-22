import pathlib
import typing

from ansible.errors import AnsibleError
from ansible.plugins.lookup import LookupBase


class Target(typing.TypedDict):
    file: str
    template: typing.NotRequired[str]
    src: typing.NotRequired[str]


class LookupModule(LookupBase):
    def run(
        self, directories: list[str], variables: dict = None, **kwargs
    ) -> list[bool]:
        self.set_options(var_options=variables, direct=kwargs)

        base = pathlib.Path(variables["ansible_search_path"][0])
        return_values = []
        for directory in directories:
            for source_key, source_dir in (
                ("template", "templates"),
                ("src", "files"),
            ):
                return_values.extend(
                    self._glob_targets(base / source_dir, directory, source_key)
                )

        return return_values

    def _glob_targets(
        self, base: pathlib.Path, directory: str, key: typing.Literal["template", "src"]
    ) -> typing.Generator[Target]:
        #
        # base is expected to be in the form:
        #  ../templates
        # source_dir is expected to be in the form:
        #  ../templates/mydir
        #
        source_dir = base.joinpath(directory)
        for dirpath, _, filenames in source_dir.walk():
            for file in filenames:
                #
                # Source includes directories provided by user,
                #  such as mydir/mytemplate.txt.j2.
                #
                source = str(dirpath.joinpath(file).relative_to(base))
                #
                # Destination is relative to the directories provided
                #  by user, such as mytemplate.txt.
                #
                destination = str(dirpath.joinpath(file).relative_to(source_dir))
                if key == "template":
                    destination = destination.removesuffix(".j2")

                yield {"file": destination, key: source}
