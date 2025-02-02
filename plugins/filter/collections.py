class FilterModule:
    def filters(self):
        return dict(
            first_or_default=self.first_or_default,
            list2dictlist=self.list2dictlist,
        )

    @staticmethod
    def first_or_default(iterable, default):
        return default if len(iterable) == 0 else next(iter(iterable))

    @staticmethod
    def list2dictlist(items, key, seed={}):
        return [{**seed, key: item} for item in items]
