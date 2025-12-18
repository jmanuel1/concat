import contextlib
import io
import sys
import unittest
from typing import Iterator, TextIO

import concat.parser_combinators
import concat.stdlib.repl
import concat.stdlib.types
import concat.typecheck
from concat.typecheck.context import change_context
from concat.typecheck.types import SequenceVariable, StackEffect, TypeSequence


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
        context = concat.typecheck.TypeChecker()
        with (
            replace_stdin(io.StringIO('some words here')),
            change_context(context),
        ):
            concat.stdlib.repl.read_quot(
                context,
                stack,
                [],
                extra_env=concat.typecheck.Environment(
                    {
                        'some': StackEffect(
                            TypeSequence(context, [seq_var]),
                            TypeSequence(context, []),
                        ),
                        'words': StackEffect(
                            TypeSequence(context, []),
                            TypeSequence(context, []),
                        ),
                        'here': StackEffect(
                            TypeSequence(context, []),
                            TypeSequence(context, []),
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
            except concat.parser_combinators.ParseError:
                self.fail('repl must recover from parser failures')
