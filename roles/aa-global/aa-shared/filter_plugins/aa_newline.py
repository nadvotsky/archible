#
# `aa_newline` represents a jinja filter that appends a newline to a source string.
#
# The rationale behind is that sometimes YAML-escaping gets a little tricky to maintain, and requires double-escaping
#  \\\\n. For all other cases, it adheres to for more concise syntax instead of `(str + "\n")` or `("{}\n".format(str))`.
#
class FilterModule:
    def filters(self):
        return dict(aa_newline=self.newline)

    @staticmethod
    def newline(string):
        return string + "\n"
