import unittest
import io
import sys
import concat.level1.stdlib.types
import concat.level1.stdlib.repl


class TestREPLFunctions(unittest.TestCase):
    def test_read_quot(self):
        original_stdin = sys.stdin
        sys.stdin = io.StringIO('some words here')
        stack = []
        # Like in Factor, read_quot will search its caller's scope for objects.
        some, words, here = object(), object(), object()
        try:
            concat.level1.stdlib.repl.read_quot(stack, [])
        finally:
            sys.stdin = original_stdin
        self.assertEqual(
            stack,
            [concat.level1.stdlib.types.Quotation([some, words, here])],
            msg='read_quot has incorrect stack effect')
