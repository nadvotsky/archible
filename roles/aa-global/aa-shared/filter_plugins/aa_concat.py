#
# `aa_concat` joins multiple iterables together.
#
# Unlike the built-in `ansible.builtin.union`, this filter does not exclude duplicates.
# Unlike the build-in `__add__` operator, this prematurely unwraps new ansible-core 2.19 errors.
#
import typing

import functools
import operator


class FilterModule:
    def filters(self):
        return dict(aa_concat=self.concat)

    @staticmethod
    def concat(lists: list[typing.Iterable]):
        return functools.reduce(operator.add, map(list, lists))
