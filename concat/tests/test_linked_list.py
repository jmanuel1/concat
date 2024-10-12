from concat.linked_list import LinkedList, empty_list
from hypothesis import given
import hypothesis.strategies as st
from typing import Callable, List
import unittest


linked_lists = st.lists(st.integers()).map(LinkedList.from_iterable)


class TestMonoid(unittest.TestCase):
    def test_empty(self) -> None:
        self.assertEqual(0, len(empty_list))
        self.assertFalse(empty_list)
        self.assertListEqual([], list(empty_list))

    @given(st.lists(st.integers()), st.lists(st.integers()))
    def test_add(self, a: List[int], b: List[int]) -> None:
        self.assertListEqual(
            a + b,
            list(LinkedList.from_iterable(a) + LinkedList.from_iterable(b)),
        )

    @given(linked_lists, linked_lists, linked_lists)
    def test_assoc(
        self, a: LinkedList[int], b: LinkedList[int], c: LinkedList[int]
    ) -> None:
        self.assertEqual((a + b) + c, a + (b + c))

    @given(linked_lists)
    def test_id(self, a: LinkedList[int]) -> None:
        self.assertEqual(a, a + empty_list)
        self.assertEqual(a, empty_list + a)


predicates = st.functions(
    like=lambda _: True, returns=st.booleans(), pure=True
)


class TestFilter(unittest.TestCase):
    @given(predicates)
    def test_empty(self, p: Callable[[int], bool]) -> None:
        self.assertEqual(empty_list, empty_list.filter(p))

    @given(linked_lists)
    def test_remove_all(self, l: LinkedList[int]) -> None:
        self.assertEqual(empty_list, l.filter(lambda _: False))

    @given(linked_lists)
    def test_keep_all(self, l: LinkedList[int]) -> None:
        self.assertEqual(l, l.filter(lambda _: True))

    @given(linked_lists, predicates)
    def test_idempotency(
        self, l: LinkedList[int], p: Callable[[int], bool]
    ) -> None:
        self.assertEqual(l.filter(p), l.filter(p).filter(p))

    @given(linked_lists, predicates)
    def test_excluded_middle(
        self, l: LinkedList[int], p: Callable[[int], bool]
    ) -> None:
        self.assertSetEqual(
            set(l), set(l.filter(p) + l.filter(lambda x: not p(x)))
        )

    @given(linked_lists, predicates)
    def test_subset(
        self, l: LinkedList[int], p: Callable[[int], bool]
    ) -> None:
        self.assertLessEqual(set(l.filter(p)), set(l))

    @given(linked_lists, predicates)
    def test_forward_observable_order(
        self, l: LinkedList[int], p: Callable[[int], bool]
    ) -> None:
        observed_order = []

        def pred(x: int) -> bool:
            observed_order.append(x)
            return p(x)

        l.filter(pred)
        self.assertListEqual(list(l), observed_order)
