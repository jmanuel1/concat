"""Python-Concat interface tests.

Tests that the boundary between Python and Concat is correct."""
import unittest
import concat.level1.stdlib.pyinterop
from typing import List, cast


class TestObjectFactories(unittest.TestCase):
    """Test the factories for Python types like int."""

    def test_to_int(self) -> None:
        """Test that to_int works."""
        stack = [10, '89']
        stash: List[object] = []
        concat.level1.stdlib.pyinterop.to_int(stack, stash)
        message = 'to_int has incorrect stack effect'
        self.assertEqual(stack, [89], msg=message)

    def test_to_bool(self) -> None:
        """Test that to_bool works."""
        stack: List[object] = [10]
        stash: List[object] = []
        concat.level1.stdlib.pyinterop.to_bool(stack, stash)
        message = 'to_bool has incorrect stack effect'
        self.assertEqual(stack, [True], msg=message)

    def test_to_float(self) -> None:
        """Test that to_float works."""
        stack: List[object] = [10]
        stash: List[object] = []
        concat.level1.stdlib.pyinterop.to_float(stack, stash)
        message = 'to_float has incorrect stack effect'
        self.assertIsInstance(
            stack[0], float, msg='to_float does not push a float')
        self.assertAlmostEqual(cast(float, stack[0]), 10.0, 0, msg=message)

    def test_to_complex(self) -> None:
        """Test that to_complex works."""
        stack: List[object] = [10, 20]
        stash: List[object] = []
        concat.level1.stdlib.pyinterop.to_complex(stack, stash)
        message = 'to_complex has incorrect stack effect'
        self.assertIsInstance(
            stack[0], complex, msg='to_complex does not push a complex')
        self.assertAlmostEqual(  # type: ignore
            stack[0], 20 + 10j, 0, msg=message)

    def test_to_slice(self) -> None:
        """Test that to_slice works."""
        stack: List[object] = [10, 20, 5]
        stash: List[object] = []
        concat.level1.stdlib.pyinterop.to_slice(stack, stash)
        message = 'to_slice has incorrect stack effect'
        self.assertEqual(stack, [slice(5, 20, 10)], msg=message)

    def test_to_str(self) -> None:
        """Test that to_str works."""
        stack: List[object] = [None, None, 5]
        stash: List[object] = []
        concat.level1.stdlib.pyinterop.to_str(stack, stash)
        message = 'to_str has incorrect stack effect'
        self.assertEqual(stack, ['5'], msg=message)

    def test_to_bytes(self) -> None:
        """Test that to_bytes works."""
        stack: List[object] = [None, None, 5]
        stash: List[object] = []
        concat.level1.stdlib.pyinterop.to_bytes(stack, stash)
        message = 'to_bytes has incorrect stack effect'
        self.assertEqual(stack, [bytes(5)], msg=message)

    def test_to_tuple(self) -> None:
        """Test that to_tuple works."""
        stack: List[object] = [[None, None, 5]]
        stash: List[object] = []
        concat.level1.stdlib.pyinterop.to_tuple(stack, stash)
        message = 'to_tuple has incorrect stack effect'
        self.assertEqual(stack, [(None, None, 5)], msg=message)

    def test_to_list(self) -> None:
        """Test that to_list works."""
        stack: List[object] = [[None, None, 5]]
        stash: List[object] = []
        concat.level1.stdlib.pyinterop.to_list(stack, stash)
        message = 'to_list has incorrect stack effect'
        self.assertEqual(stack, [[None, None, 5]], msg=message)

    def test_to_bytearray(self) -> None:
        """Test that to_bytearray works."""
        stack: List[object] = [None, None, 5]
        stash: List[object] = []
        concat.level1.stdlib.pyinterop.to_bytearray(stack, stash)
        message = 'to_list has incorrect stack effect'
        self.assertEqual(stack, [bytearray(5)], msg=message)
