from concat.orderedset import InsertionOrderedSet
from hypothesis import given  # type: ignore
import hypothesis.strategies as st  # type: ignore
from typing import List, Set
import unittest


class TestInsertionOrderedSet(unittest.TestCase):
    @given(st.sets(st.integers()).map(list))
    def test_insertion_from_list_preserves_order(self, l: List[int]) -> None:
        self.assertListEqual(l, list(InsertionOrderedSet(l)))

    @given(st.sets(st.integers()), st.sets(st.integers()))
    def test_set_difference_preserves_order(
        self, original: Set[int], to_remove: Set[int]
    ) -> None:
        insertion_order_set = InsertionOrderedSet[int](list(original))
        expected_order = [x for x in insertion_order_set if x not in to_remove]
        insertion_order_set -= to_remove
        actual_order = list(insertion_order_set)
        self.assertListEqual(expected_order, actual_order)

    @given(st.sets(st.integers()), st.sets(st.integers()))
    def test_union_preserves_order(
        self, original: Set[int], to_add: Set[int]
    ) -> None:
        insertion_order_set = InsertionOrderedSet[int](list(original))
        insertion_order_to_add = InsertionOrderedSet[int](list(to_add))
        expected_order = list(insertion_order_set)
        for x in insertion_order_to_add:
            if x not in expected_order:
                expected_order.append(x)
        insertion_order_set = insertion_order_set | insertion_order_to_add
        actual_order = list(insertion_order_set)
        self.assertListEqual(expected_order, actual_order)
