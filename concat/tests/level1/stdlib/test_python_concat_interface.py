"""Python-Concat interface tests.

Tests that the boundary between Python and Concat is correct."""
import unittest
import concat.level1.stdlib.pyinterop
from typing import List


class TestObjectFactories(unittest.TestCase):
    """Test the factories for Python types like int."""

    def test_to_int(self) -> None:
        """Test that to_int works."""
        stack = [10, '89']
        stash: List[object] = []
        concat.level1.stdlib.pyinterop.to_int(stack, stash)
        message = 'py_call has incorrect stack effect'
        self.assertEqual(stack, [89], msg=message)
