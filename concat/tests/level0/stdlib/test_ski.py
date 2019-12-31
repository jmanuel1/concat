import concat.level0.stdlib.ski
import unittest
from typing import List


class TestCombinators(unittest.TestCase):

    def setUp(self) -> None:
        pass

    def __test_function(self, stack: List[object], stash: List[object]) -> None:
        stack.append('test')

    def test_i(self) -> None:
        stack = [self.__test_function]
        concat.level0.stdlib.ski.i(stack, [])
        self.assertEqual(['test'], stack, msg='i has incorrect stack effect')

    def test_s(self) -> None:
        stack = ['c', 'b', self.__test_function]
        concat.level0.stdlib.ski.s(stack, [])
        self.assertEqual([['c', 'b'], 'c', 'test'], stack, msg='s has incorrect stack effect')

    def test_k(self) -> None:
        stack = ['b', self.__test_function]
        concat.level0.stdlib.ski.k(stack, [])
        self.assertEqual(['test'], stack, msg='k has incorrect stack effect')