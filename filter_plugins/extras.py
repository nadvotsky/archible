#!/usr/bin/env python

import inspect


class FilterModule:
    def filters(self):
        def method_filter(m):
            return (
                (inspect.isfunction(m) or inspect.ismethod(m))
                and not m.__name__.startswith("_")
                and not m.__name__ == self.filters.__name__
            )

        return dict(inspect.getmembers(self, method_filter))

    #
    # `relative_indent` is a lightweight filter plugin that splits the specified string by lines, filters them, and adds
    #  the required intendation.
    #
    @staticmethod
    def relative_indent(string, tab=False, space=0, times=0):
        lines = string.strip().splitlines()
        prepend = ("\t" if tab else (" " * space)) * times

        mask = [False if i == 0 else bool(line.strip()) for i, line in enumerate(lines)]
        if not any(mask):
            return string.strip()

        block_base = min([
            len(lines[i]) - len(lines[i].lstrip()) for i, m in enumerate(mask) if m is True
        ])

        return "\n".join([
            (prepend + lines[i][block_base:]) if m else lines[i]
            for i, m in enumerate(mask)
        ])


    @staticmethod
    def workspace_prefix(mon_name, is_first):
        return "" if is_first else mon_name[0].upper()

    @staticmethod
    def andnewline(string):
        return string + ("\n" if len(string) else "")

    @staticmethod
    def newline(string):
        return string + "\n"

    @staticmethod
    def quote(string):
        return '"{}"'.format(string)

    @staticmethod
    def escaped_quote(string):
        return '\\"{}\\"'.format(string)

    @staticmethod
    def scale(value, real):
        return round(value * real)
