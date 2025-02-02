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

    @staticmethod
    def scale(value, real):
        return round(value * real)
