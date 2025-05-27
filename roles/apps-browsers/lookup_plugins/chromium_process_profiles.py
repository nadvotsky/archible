import os.path
import operator

from ansible.plugins.lookup import LookupBase


class LookupModule(LookupBase):
    def process(self, home, matches, destructive):
        profiles = list(filter(
            lambda match: match != os.path.join(home, "System Profile"),
            map(os.path.dirname, map(operator.itemgetter("path"), matches))
        ))
        if not profiles:
            return dict(
                default=True,
                creates=[os.path.join(home, "Default")],
                patches=[],
            )

        return dict(
            default=False,
            creates=profiles,
            patches=profiles if destructive else [],
        )

    def run(self, args, variables, **kwargs):
        self.set_options(var_options=variables, direct=kwargs)

        return [
            self.process(args[0], args[1]["files"], variables["policy"]["destructive"])
        ]
