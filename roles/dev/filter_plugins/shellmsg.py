#!/usr/bin/env python
# TODO: @deprecated: use README.md instead.

class FilterModule:
    def filters(self):
        return dict(shellmsg=self.shellmsg)

    SHELLMSG_SEP = "echo \"{}\"".format("-" * 80)

    @classmethod
    def shellmsg(cls, sections, title):
        max_key_len = max((len(key) for section in sections for key in section.keys()))
        lines = [cls.SHELLMSG_SEP, f"echo \"{title}\"", cls.SHELLMSG_SEP]
        for section in sections:
            for key, value in section.items():
                lines.append(f'echo "{key.title().ljust(max_key_len)}: {value}"')

            lines.append(cls.SHELLMSG_SEP)

        return " &&\n".join(lines)
