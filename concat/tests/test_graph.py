from concat.graph import cycles
from unittest import TestCase


class TestCycles(TestCase):
    def test_empty(self) -> None:
        with self.assertRaises(StopIteration):
            next(cycles({}))

    def test_singleton(self) -> None:
        it = cycles({1: []})
        self.assertListEqual([*next(it)], [1])
        with self.assertRaises(StopIteration):
            next(it)

    def test_cycle(self) -> None:
        it = cycles({1: [2], 2: [1]})
        self.assertListEqual([*sorted(next(it))], [1, 2])
        with self.assertRaises(StopIteration):
            next(it)

    def test_self_loop(self) -> None:
        it = cycles({1: [1]})
        self.assertListEqual([*next(it)], [1])
        with self.assertRaises(StopIteration):
            next(it)

    def test_two_strongly_connected_components(self) -> None:
        it = cycles({1: [2], 2: [1, 3], 3: []})
        self.assertListEqual([*sorted(next(it))], [1, 2])
        self.assertListEqual([*sorted(next(it))], [3])
        with self.assertRaises(StopIteration):
            next(it)

    def test_pointing_back_at_cycle(self) -> None:
        it = cycles({1: [2], 2: [1], 3: [1]})
        self.assertListEqual([*sorted(next(it))], [1, 2])
        self.assertListEqual([*sorted(next(it))], [3])
        with self.assertRaises(StopIteration):
            next(it)
