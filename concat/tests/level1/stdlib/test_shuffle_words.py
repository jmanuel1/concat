import concat.level1.stdlib.shuffle_words
import concat.level0.stdlib.types
import unittest
from typing import List, cast, Callable


class TestShuffleWords(unittest.TestCase):

    def setUp(self) -> None:
        pass

    def __test_function(self, stack: List[object], stash: List[object]) -> None:
        stack.append(stack.pop())

    def test_drop(self) -> None:
        stack = [5, self.__test_function]
        concat.level1.stdlib.shuffle_words.drop(stack, [])
        self.assertEqual([5], stack, msg='drop has incorrect stack effect')

    def test_drop_2(self) -> None:
        stack = [5, self.__test_function]
        concat.level1.stdlib.shuffle_words.drop_2(stack, [])
        self.assertEqual([], stack, msg='drop_2 has incorrect stack effect')

    def test_drop_3(self) -> None:
        stack = [5, self.__test_function, 42]
        concat.level1.stdlib.shuffle_words.drop_3(stack, [])
        self.assertEqual([], stack, msg='drop_3 has incorrect stack effect')

    def test_nip(self) -> None:
        stack = [5, self.__test_function, 42]
        concat.level1.stdlib.shuffle_words.nip(stack, [])
        self.assertEqual([5, 42], stack, msg='nip has incorrect stack effect')

    def test_nip_2(self) -> None:
        stack = [5, self.__test_function, 42]
        concat.level1.stdlib.shuffle_words.nip_2(stack, [])
        self.assertEqual([42], stack, msg='nip_2 has incorrect stack effect')

    def test_dup(self) -> None:
        stack = [5, self.__test_function, 42]
        concat.level1.stdlib.shuffle_words.dup(stack, [])
        self.assertEqual([5, self.__test_function, 42, 42], stack, msg='dup has incorrect stack effect')

    def test_dup_2(self) -> None:
        stack = [5, self.__test_function, 42]
        concat.level1.stdlib.shuffle_words.dup_2(stack, [])
        self.assertEqual([5, self.__test_function, 42, self.__test_function, 42], stack, msg='dup_2 has incorrect stack effect')

    def test_swap(self) -> None:
        stack = [5, self.__test_function, 42]
        concat.level1.stdlib.shuffle_words.swap(stack, [])
        self.assertEqual([5, 42, self.__test_function], stack, msg='swap has incorrect stack effect')

    def test_dup_3(self) -> None:
        stack = [5, self.__test_function, 42]
        concat.level1.stdlib.shuffle_words.dup_3(stack, [])
        self.assertEqual([5, self.__test_function, 42]*2, stack, msg='dup_3 has incorrect stack effect')

    def test_over(self) -> None:
        stack = [5, self.__test_function, 42]
        concat.level1.stdlib.shuffle_words.over(stack, [])
        self.assertEqual([5, self.__test_function, 42, self.__test_function], stack, msg='over has incorrect stack effect')

    def test_over_2(self) -> None:
        stack = [5, self.__test_function, 42]
        concat.level1.stdlib.shuffle_words.over_2(stack, [])
        self.assertEqual([5, self.__test_function, 42, 5, self.__test_function], stack, msg='over_2 has incorrect stack effect')

    def test_pick(self) -> None:
        stack = [5, self.__test_function, 42]
        concat.level1.stdlib.shuffle_words.pick(stack, [])
        self.assertEqual([5, self.__test_function, 42, 5], stack, msg='pick has incorrect stack effect')
