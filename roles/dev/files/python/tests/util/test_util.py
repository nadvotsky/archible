import pytest

import util


#
# GIVEN-WHEN-THEN or SHOULD-WHEN
#
def test_join_strings_concatenates_with_comma_and_space(words) -> None:
    assert util.join_strings(*words) == "One, Two"
