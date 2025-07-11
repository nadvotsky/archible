#
# `aa_relindent` is a jinja filter that can be used in complicated configuration rendering scenarios, where underlying
#  block needs to be properly indented.
#
# Due to the jinja being mainly focused on non-permissive markup languages such as HTML, no additional indentaion
#  control features are available. In case of strict spacing demands such as configuration scripts, this may bring some
#  complications.
#
# `aa_relindent` seeks the most lightweight, in-place solution and does not solve the problem entirely. It allows to use
#  the existing codebase without major modifications. For more radical prototype, take a look at the following:
#   - foundation.legacy.template_plus
#   - https://github.com/stereobutter/jinja2_workarounds
#   - https://github.com/dldevinc/jinja2-indent
#
# This filter basically splits the specified string by lines, filters them, and adds the required intendation.
# For example:
#
# <space>config_entry = true
# <space>{{ "one = true\ntwo = false" | aa_relindent(space=4, times=1) }}
#
# Is going to be rendered as:
#
# <space>config_entry = true
# <space>one = true
# <space>two = true
#
class FilterModule:
    def filters(self):
        return dict(aa_relindent=self.relative_indent)

    @staticmethod
    def relative_indent(string, tab=False, space=0, times=0):
        lines = string.strip().splitlines()
        prepend = ("\t" if tab else (" " * space)) * times

        mask = [False if i == 0 else bool(line.strip()) for i, line in enumerate(lines)]
        if not any(mask):
            return string.strip()

        block_base = min([len(lines[i]) - len(lines[i].lstrip()) for i, m in enumerate(mask) if m is True])

        return "\n".join([(prepend + lines[i][block_base:]) if m else lines[i] for i, m in enumerate(mask)])
