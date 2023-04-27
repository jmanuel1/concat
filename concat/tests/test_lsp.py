from concat.lsp import index_to_utf16_code_unit_offset
from hypothesis import given
from hypothesis.strategies import composite, integers, text
from typing import Tuple
from unittest import TestCase


@composite
def strings_with_index(draw) -> Tuple[str, int]:
    string = draw(text(min_size=1))
    index = draw(integers(min_value=0, max_value=len(string) - 1))
    return string, index


class TestTextEncoding(TestCase):
    @given(strings_with_index())
    def test_index_to_utf16_code_unit_offset(
        self, string_with_index: Tuple[str, int]
    ) -> None:
        string, index = string_with_index
        actual = index_to_utf16_code_unit_offset(string, index)
        expected = len(string[:index].encode('utf-16-le')) / 2
        self.assertEqual(actual, expected)
