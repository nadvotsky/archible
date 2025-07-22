#
# `aa_newline` - jinja filter that wraps a string into quotes.
#
# Unlike `quote`, this is not suitable for shell and quotes the string unconditionaly.
#
class FilterModule:
    def filters(self):
        return dict(aa_dquote=self.dquote, aa_squote=self.squote)

    @staticmethod
    def dquote(string):
        return "\"{}\"".format(string)

    @staticmethod
    def squote(string):
        return "'{}'".format(string)
