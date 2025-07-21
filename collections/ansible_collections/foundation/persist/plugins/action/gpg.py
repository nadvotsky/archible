#
# foundation.persist.gpg - retrieve previously generated gpg keys metadata.
#
# Follow the project README for more information.
#

import json
import os.path
import base64

from ansible.errors import AnsibleActionFail
from ansible.plugins.action import ActionBase

from ansible_collections.foundation.util.types import RawResult, TaskVars
from ansible_collections.foundation.util.specs import validate_spec


ARGS_SPEC = {
    "home": {
        "type": "path",
        "required": True,
    },
    "layout": {
        "type": "str",
        "choice": ["xdg", "dot"],
        "required": True,
    },
}

VARS_SPEC = {
    "keys": {
        "type": "list",
        "elements": "str",
        "required": True,
    },
}


class ActionModule(ActionBase):
    _ARCHIVE_FILE = "unattended-keys.json"

    def _employ_inputs(self) -> tuple[str, list[str] | None]:
        _, args = self.validate_argument_spec(ARGS_SPEC)
        if args["layout"] == "dot":
            path = os.path.join(args["home"], ".gnupg", self._ARCHIVE_FILE)
        elif args["layout"] == "xdg":
            path = os.path.join(args["home"], ".local", "share", self._ARCHIVE_FILE)
        else:
            raise AnsibleActionFail("Unreachable layout")

        keys = validate_spec(VARS_SPEC, self._templar.template(self._task.vars))["keys"]

        #
        # 'all' is a special value for retrieving all keys.
        #
        return path, None if keys == ["all"] else keys

    def _read_unattended(self, path: str, task_vars: TaskVars) -> dict:
        result = self._execute_module(
            module_name="ansible.builtin.slurp",
            module_args=dict(src=path),
            task_vars=task_vars,
        )
        if result.get("failed"):
            raise AnsibleActionFail(f"Unable to read '{path}'", result)

        return json.loads(base64.b64decode(result["content"].encode()))

    def run(self, tmp: None = None, task_vars: TaskVars = None) -> RawResult:
        path, keys = self._employ_inputs()
        unattended_keys = self._read_unattended(path, task_vars)

        #
        # Results are stored in the `gpg` subdictionary to allow for loops, filters, and other manipulations.
        #
        result = RawResult(gpg={})
        #
        # If no specific key is requested (`keys` is None), process all available keys.
        #
        for key in (keys or unattended_keys.keys()):
            if key not in unattended_keys:
                raise AnsibleActionFail(f"No such GnuPG key '{key}'")

            result["gpg"][key] = unattended_keys[key]

        return result
