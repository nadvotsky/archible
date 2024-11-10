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


    DEFAULT_REPLACEMENTS = dict(enumerate(["black", "red", "green", "yellow", "blue", "purple", "cyan", "white"]))
    ANSI_TABLE_SIZE = 8

    @classmethod
    def _parse_ansi_preset(cls, item_group, item, lookup, code_to_name, mod, sep):
        try:
            mode_alt = False
            position = lookup.index(item)
            ansi = (30 if position < cls.ANSI_TABLE_SIZE else 90) + position % cls.ANSI_TABLE_SIZE
            name = code_to_name[position % cls.ANSI_TABLE_SIZE]
            modifier = mod if position >= cls.ANSI_TABLE_SIZE else None
        except ValueError:
            mode_alt = True
            position = None
            ansi = None
            name = item
            modifier = None

        return {
            "mode_alt": mode_alt,
            "modifiers": modifier,
            "raw_key": position,
            "ansi": ansi,
            "key": name,
            "line": sep.join(filter(None, [modifier, name])),
        }

    @classmethod
    def parse_ansi_presets(cls, preset, ansi, replacements={}, mod="bright", sep="-"):
        assert all(
            (len(item) == cls.ANSI_TABLE_SIZE for item in ansi.values())
        ), "Size of the ansi table must be exactly 8 elements"

        code_to_name = {**cls.DEFAULT_REPLACEMENTS, **replacements}
        lookup = ansi["normal"] + ansi["bright"]

        return {
            name: parsed
            for name, color in preset.items()
            if (parsed := cls._parse_ansi_preset(name, color, lookup, code_to_name, mod, sep)) is not None
        }

    @staticmethod
    def is_tagged(tags, ansible_run_tags, ansible_skip_tags):
        tags, ansible_run_tags, ansible_skip_tags = map(frozenset, (tags, ansible_run_tags, ansible_skip_tags))

        if not tags.isdisjoint(ansible_skip_tags):
            return False

        if "all" in ansible_run_tags:
            return True

        return not tags.isdisjoint(ansible_run_tags)

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
