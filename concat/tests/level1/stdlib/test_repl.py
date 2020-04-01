import unittest
import io
import sys
import contextlib
import concat.level1.stdlib.types
import concat.level1.stdlib.repl
from typing import TextIO, Iterator


@contextlib.contextmanager
def replace_stdin(input_stream: TextIO) -> Iterator[None]:
    # don't use sys.__stdin__ because sys.stdin might not be the original one
    original_stdin = sys.stdin
    sys.stdin = input_stream
    try:
        yield
    finally:
        sys.stdin = original_stdin


class TestREPLFunctions(unittest.TestCase):
    def test_read_quot(self):
        stack = []
        # Like in Factor, read_quot will search its caller's scope for objects.
        some, words, here = object(), object(), object()
        with replace_stdin(io.StringIO('some words here')):
            concat.level1.stdlib.repl.read_quot(stack, [])
        self.assertEqual(
            stack,
            [concat.level1.stdlib.types.Quotation([some, words, here])],
            msg='read_quot has incorrect stack effect')

    def test_do_return(self):
        self.assertRaises(concat.level1.stdlib.repl.REPLExitException,
                          concat.level1.stdlib.repl.do_return, [], [])
