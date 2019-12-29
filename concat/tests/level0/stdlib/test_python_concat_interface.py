"""Python-Concat interface tests.

Tests that the boundary between Python and Concat is correct."""
import concat.libconcat as libconcat
import unittest
import unittest.mock as mock
import concat.stdlib.builtins as builtins
from concat.level0.stdlib.types import Quotation
import concat.level0.stdlib.pyinterop


class TestIntoPythonFromConcat(unittest.TestCase):
    """Test the Python-Concat interface going into Python from Concat."""

    def test_python_function(self):
        """Python function call test (from Concat).

        Test that a normal Python is treated as if it had the stack effect
        kwargs args -- func(*args, **kwargs) when called with py_call."""
        stack, stash = [Quotation([]), Quotation([0]), bool], []
        concat.level0.stdlib.pyinterop.py_call(stack, stash)
        self.assertEqual(stack, [False], msg='py_call has incorrect stack effect')
