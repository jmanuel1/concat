import unittest
import io
import sys
import contextlib
import concat.parse
import concat.typecheck
from concat.typecheck.types import SequenceVariable, StackEffect, TypeSequence
import concat.stdlib.types
import concat.stdlib.repl
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
    def test_read_quot(self) -> None:
        stack = []
        seq_var = SequenceVariable()
        # Like in Factor, read_quot will search its caller's scope for objects.
        some, words, here = object(), object(), object()
        with replace_stdin(io.StringIO('some words here')):
            concat.stdlib.repl.read_quot(
                stack,
                [],
                extra_env=concat.typecheck.Environment(
                    {
                        'some': StackEffect(
                            TypeSequence([seq_var]), TypeSequence([])
                        ),
                        'words': StackEffect(
                            TypeSequence([]), TypeSequence([])
                        ),
                        'here': StackEffect(
                            TypeSequence([]), TypeSequence([])
                        ),
                    }
                ),
            )
        self.assertEqual(
            stack,
            [concat.stdlib.types.Quotation([some, words, here])],
            msg='read_quot has incorrect stack effect',
        )

    def test_repl(self):
        with replace_stdin(io.StringIO('[,] [,] $input py_call\nhi there')):
            concat.stdlib.repl.repl([], [])
            self.assertEqual(
                sys.stdin.read(), '', msg='repl did not consume all input'
            )

    def test_catch_parse_errors(self):
        with replace_stdin(io.StringIO('drg nytu y,i.')):
            try:
                concat.stdlib.repl.repl([], [])
            except concat.parse.ParseError:
                self.fail('repl must recover from parser failures')
