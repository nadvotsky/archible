#
# foundation.user.layout - evaluate effective user layout value.
#
# Follow the project README for more information.
#

from ansible.plugins.lookup import LookupBase

from ansible_collections.foundation.user.plugins.module_utils.operations import (
    Operations,
    Conclusion,
)


class LookupModule(LookupBase):
    def run(self, inputs: list[str, dict], variables: dict = None, **kwargs) -> list[bool]:
        self.set_options(var_options=variables, direct=kwargs)

        layout, choice = inputs
        ops = Operations(layout, "never")

        generator = (
            con.value for con in ops.lookup(choice) if con.descriptor in (Conclusion.DS_RESOLVED, Conclusion.OP_NONE)
        )
        return [next(generator)]
