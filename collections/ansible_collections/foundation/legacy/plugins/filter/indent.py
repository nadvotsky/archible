class FilterModule:
    def filters(self):
        return dict(relative_indent=self.relative_indent)

    @staticmethod
    def relative_indent(string, tab=False, space=0, times=0):
        lines = string.strip().splitlines()
        prepend = ("\t" if tab else (" " * space)) * times

        mask = [False if i == 0 else bool(line.strip()) for i, line in enumerate(lines)]
        if not any(mask):
            return string.strip()

        block_base = min([len(lines[i]) - len(lines[i].lstrip()) for i, m in enumerate(mask) if m is True])

        return "\n".join([(prepend + lines[i][block_base:]) if m else lines[i] for i, m in enumerate(mask)])
