import functools
import operator

from ansible.plugins.lookup import LookupBase
from ansible.utils.vars import merge_hash


class LookupModule(LookupBase):
    MERGER = staticmethod(functools.partial(merge_hash, list_merge="append"))

    def run(self, *args: None, variables: dict = None, **kwargs) -> list[dict]:
        self.set_options(var_options=variables, direct=kwargs)

        store, merged = self._templar.template(variables["dev"]["cplusplus"]["toolchains"]), {}
        for key, val in store.items():
            if val.get("intermediate", False) is True:
                continue
            elif len(val.get("inherits", [])) == 0:
                merged[key] = val
                continue

            parents = operator.itemgetter(*val["inherits"])(store)
            parents = list(parents) if isinstance(parents, tuple) else [parents]
            merged[key] = functools.reduce(self.MERGER, parents + [val])

            for important in ("inherits", "default", "intermediate"):
                if important in val:
                    merged[key][important] = val[important]
                else:
                    merged[key].pop(important, None)

        return [merged]
