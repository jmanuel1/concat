import concat.stdlib.execution
import concat.stdlib.types
import unittest
from typing import List, cast, Callable


class TestCombinators(unittest.TestCase):
    """Test the execution flow combinators.

    call is not tested because that is in pyinterop.
    """

    def setUp(self) -> None:
        pass

    def __test_function(
        self, stack: List[object], stash: List[object]
    ) -> None:
        stack.append(stack.pop())

    def __test_function_2(
        self, stack: List[object], stash: List[object]
    ) -> None:
        stack.append(42)

    def test_choose(self) -> None:
        stack = [False, self.__test_function, self.__test_function_2]
        concat.stdlib.execution.choose(stack, [])
        self.assertEqual([42], stack, msg='choose has incorrect stack effect')

    def test_if_then(self) -> None:
        stack = [False, self.__test_function]
        concat.stdlib.execution.if_then(stack, [])
        self.assertEqual([], stack, msg='if_then has incorrect stack effect')

    def test_if_not(self) -> None:
        stack = [5, False, self.__test_function]
        concat.stdlib.execution.if_not(stack, [])
        self.assertEqual([5], stack, msg='if_not has incorrect stack effect')

    def test_case(self) -> None:
        stack = [5, False, self.__test_function]
        concat.stdlib.execution.case(stack, [])
        self.assertEqual([5], stack, msg='case has incorrect stack effect')

    def test_loop(self) -> None:
        stack = [False, self.__test_function]
        concat.stdlib.execution.loop(stack, [])
        self.assertEqual([], stack, msg='loop has incorrect stack effect')
