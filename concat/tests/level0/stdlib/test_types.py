import concat.level0.stdlib.types
import unittest
from typing import List, Callable


class TestQuotations(unittest.TestCase):

    def __push(self, value: object) -> Callable[[List[object], List[object]], None]:
        return lambda stack, _: stack.append(value)

    def test_quotation_is_callable(self) -> None:
        quote = concat.level0.stdlib.types.Quotation([self.__push('c')])
        stack = []
        quote(stack, [])
        self.assertEqual(['c'], stack, msg='quotations do not behave correctly when called')
