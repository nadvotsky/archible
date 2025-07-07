from ansible.plugins.lookup import LookupBase


class LookupModule(LookupBase):
    def run(self, tags: list[str], variables: dict = None, **kwargs) -> list[bool]:
        self.set_options(var_options=variables, direct=kwargs)

        tags, run_tags, skip_tags = map(
            frozenset,
            (tags, variables["ansible_run_tags"], variables["ansible_skip_tags"]),
        )

        if not tags.isdisjoint(skip_tags):
            return [False]
        elif "all" in run_tags:
            return [True]

        return [not tags.isdisjoint(run_tags)]
