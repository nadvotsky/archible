class FilterModule:
    def filters(self):
        return dict(ga_scale=self.scale, ga_workspace_prefix=self.workspace_prefix)

    @staticmethod
    def scale(value, real):
        return round(value * real)

    @staticmethod
    def workspace_prefix(mon_name, is_first):
        return "" if is_first else mon_name[0].upper()
