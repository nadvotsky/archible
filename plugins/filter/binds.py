class FilterModule:
    def filters(self):
        return dict(
            parse_ansi_presets=self.parse_ansi_presets,
            parse_binds=self.parse_binds,
            parse_bind=self.parse_bind,
        )

    DEFAULT_REPLACEMENTS = dict(
        enumerate(
            ["black", "red", "green", "yellow", "blue", "purple", "cyan", "white"]
        )
    )
    ANSI_TABLE_SIZE = 8

    @classmethod
    def _parse_ansi_preset(cls, item_group, item, lookup, code_to_name, mod, sep):
        try:
            mode_alt = False
            position = lookup.index(item)
            ansi = (
                30 if position < cls.ANSI_TABLE_SIZE else 90
            ) + position % cls.ANSI_TABLE_SIZE
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
            if (
                parsed := cls._parse_ansi_preset(
                    name, color, lookup, code_to_name, mod, sep
                )
            )
            is not None
        }

    @staticmethod
    def _parse_bind_mode(bind):
        mode, alt, key = None, False, []

        for expr in bind.split(" "):
            if expr == ":alt":
                alt = True
            elif expr.startswith(":"):
                mode = expr.lstrip(":")
            else:
                key.append(expr)

        assert len(key) == 1, f"bind expression must contain exactly one key ({bind})"
        assert bool(mode) is True, "bind expression must contain the name of the mode"

        return mode, alt, key[0]

    @staticmethod
    def _parse_bind_modifiers(mode, alt, modifiers, action):
        bind_modifiers = {
            "super": False,
            "alt": False,
            "ctrl": False,
            "shift": False,
        }

        exprs = [
            modifiers[mode]["alt" if alt else "main"],
            *[
                modifiers["extra"][k]
                for k in ["word", "many", "select"]
                if action[k] is True
            ],
        ]

        for expr in filter(None, exprs):
            for modifier in expr.split("+"):
                bind_modifiers[modifier.lower()] = True

        return bind_modifiers

    @staticmethod
    def _parse_bind_key(key, keys_map, shift, merge_shift):
        if not (shift and merge_shift):
            return False, keys_map.get(key, key)

        def shift_pipe(k):
            if k is None:
                return None
            elif len(k) == 1 and k.islower():
                return chr(ord(key) - 32)

            return {
                "1": "!",
                "2": "@",
                "3": "#",
                "4": "$",
                "5": "%",
                "6": "^",
                "7": "&",
                "8": "*",
                "9": "(",
                "0": ")",
                "-": "_",
                "=": "+",
                ";": ":",
                "'": '"',
                "[": "{",
                "]": "}",
                "\\": "|",
                ",": "<",
                ".": ">",
                "/": "?",
                "Tilde": "~",
            }.get(key)

        replacement = shift_pipe(key) or shift_pipe(keys_map.get(key))
        new_key = replacement or key
        return replacement is not None, keys_map.get(new_key, new_key)

    @classmethod
    def parse_bind(
        cls,
        bind,
        user_action,
        keys,
        modifiers_map={},
        keys_map={},
        sep=("+", " "),
        merge_shift=False,
    ):
        action = {
            "name": None,
            "subs": None,
            "word": False,
            "many": False,
            "select": False,
        }
        if isinstance(user_action, dict):
            action.update(user_action)
        else:
            action["subs"] = user_action

        mode, alt, raw_key = cls._parse_bind_mode(bind)
        modifiers = cls._parse_bind_modifiers(mode, alt, keys["modifiers"], action)
        is_merged, key = cls._parse_bind_key(
            raw_key, keys_map, modifiers["shift"], merge_shift
        )

        modifiers_line = sep[0].join(
            [
                modifiers_map.get(modifier, modifier)
                for modifier, status in modifiers.items()
                if status is True and not (is_merged is True and modifier == "shift")
            ]
        )

        return {
            "action": action,
            "mode_name": mode,
            "mode_alt": alt,
            "raw_key": raw_key,
            "raw_modifiers": modifiers,
            "key": key,
            "modifiers": modifiers_line,
            "merge_shift": merge_shift,
            "line": sep[1].join(filter(None, (modifiers_line, key))),
        }

    @classmethod
    def parse_binds(
        cls,
        keys,
        actions_map,
        modifiers_map={},
        keys_map={},
        sep=("+", " "),
        merge_shift=False,
    ):
        for action_name, user_action in actions_map:
            action = {"name": action_name}
            if isinstance(user_action, dict):
                action.update(user_action)
            else:
                action["subs"] = user_action

            for bind in keys["binds"][action_name]:
                yield cls.parse_bind(
                    bind, action, keys, modifiers_map, keys_map, sep, merge_shift
                )
