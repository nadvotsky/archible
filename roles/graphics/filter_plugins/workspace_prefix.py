#!/usr/bin/env python


class FilterModule:
    def filters(self):
        return dict(workspace_prefix=self.workspace_prefix)

    @staticmethod
    def workspace_prefix(mon_name, is_first):
        return "" if is_first else mon_name[0].upper()
