class FilterModule:
    DEFAULT_REPLACEMENTS = dict(enumerate(["black", "red", "green", "yellow", "blue", "purple", "cyan", "white"]))
    ANSI_TABLE_SIZE = 8

    def filters(self):
        return dict(ga_parse_ansi=self.parse_ansi_presets)

    @classmethod
    def _parse_ansi(cls, item, lookup, code_to_name, mod, sep):
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
        assert all((len(item) == cls.ANSI_TABLE_SIZE for item in ansi.values())), (
            "Size of the ansi table must be exactly 8 elements"
        )

        code_to_name = {**cls.DEFAULT_REPLACEMENTS, **replacements}
        lookup = ansi["normal"] + ansi["bright"]

        return {
            name: parsed
            for name, color in preset.items()
            if (parsed := cls._parse_ansi(color, lookup, code_to_name, mod, sep)) is not None
        }
