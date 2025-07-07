class FilterModule:
    def filters(self):
        return dict(newline=self.newline, quote=self.quote, squote=self.squote)

    @staticmethod
    def newline(string):
        return string + "\n"

    @staticmethod
    def quote(string):
        return '"{}"'.format(string)

    @staticmethod
    def squote(string):
        return "'{}'".format(string)
