from concat.graph import cycles
from unittest import TestCase


class TestCycles(TestCase):
    def test_empty(self) -> None:
        with self.assertRaises(StopIteration):
            next(cycles({}))

    def test_singleton(self) -> None:
        it = {frozenset(c) for c in cycles({1: []})}
        self.assertEqual({frozenset([1])}, it)

    def test_cycle(self) -> None:
        it = {frozenset(c) for c in cycles({1: [2], 2: [1]})}
        self.assertEqual({frozenset([1, 2])}, it)

    def test_self_loop(self) -> None:
        it = {frozenset(c) for c in cycles({1: [1]})}
        self.assertEqual({frozenset([1])}, it)

    def test_two_strongly_connected_components(self) -> None:
        it = {frozenset(c) for c in cycles({1: [2], 2: [1, 3], 3: []})}
        self.assertIn({1, 2}, it)
        self.assertIn({3}, it)

    def test_pointing_back_at_cycle(self) -> None:
        it = {frozenset(c) for c in cycles({1: [2], 2: [1], 3: [1]})}
        self.assertIn({1, 2}, it)
        self.assertIn({3}, it)
