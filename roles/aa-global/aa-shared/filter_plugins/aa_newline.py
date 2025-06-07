class FilterModule:
    def filters(self):
        return dict(aa_newline=self.newline)

    @staticmethod
    def newline(string):
        return string + "\n"
