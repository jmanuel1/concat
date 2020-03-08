import concat.level1.stdlib.compositional
import concat.level0.stdlib.types
import unittest
from typing import List, cast


class TestCombinators(unittest.TestCase):

    def setUp(self) -> None:
        pass

    def __test_function(self,
                        stack: List[object], stash: List[object]) -> None:
        stack.append(stack.pop())

    def test_curry(self) -> None:
        stack = [5, self.__test_function]
        concat.level1.stdlib.compositional.curry(stack, [])
        self.assertIsInstance(
            stack[-1], concat.level0.stdlib.types.Quotation,
            msg='curry has incorrect stack effect')
        # call the new function
        cast(concat.level0.stdlib.types.Quotation, stack.pop())(stack, [])
        self.assertEqual([5], stack, msg='curry has incorrect stack effect')
