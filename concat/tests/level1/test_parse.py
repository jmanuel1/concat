"""Tests that the level 1 parser accepts valid level 1 token streams."""
import concat.level0.parse
import concat.level1.parse
from concat.level0.lex import Token
import unittest
from typing import Tuple, Iterable
import parsy


TokenTuple = Tuple[str, str, Tuple[int, int], Tuple[int, int]]


def to_token(tupl: TokenTuple) -> Token:
    token = Token()
    token.type, token.value, token.start, token.end = tupl
    return token


def to_tokens(*tokTuples: TokenTuple) -> Iterable[Token]:
    for tupl in tokTuples:
        yield to_token(tupl)


class TestSmallExamples(unittest.TestCase):
    examples = {
        'None\n': to_tokens(  # newline is important
            ('ENCODING', 'utf-8', (0, 0), (0, 0)),
            ('NONE', 'None', (1, 0), (1, 4)),
            ('NEWLINE', '\n', (1, 4), (1, 5)),
            ('ENDMARKER', '', (2, 0), (2, 0))
        ),
        'NotImplemented\n': to_tokens(  # newline is important
            ('ENCODING', 'utf-8', (0, 0), (0, 0)),
            ('NOTIMPL', 'NotImplemented', (1, 0), (1, 14)),
            ('NEWLINE', '\n', (1, 14), (1, 15)),
            ('ENDMARKER', '', (2, 0), (2, 0))
        )
    }

    def test_examples(self) -> None:
        for example in type(self).examples:
            with self.subTest(example=example):
                tokens = type(self).examples[example]
                parsers = concat.level0.parse.ParserDict()
                parsers.extend_with(concat.level0.parse.level_0_extension)
                parsers.extend_with(concat.level1.parse.level_1_extension)

                # for example programs, we only test acceptance

                try:
                    parsers.parse(tuple(tokens))
                except parsy.ParseError:
                    message = '{} was not accepted by the parser'.format(
                        repr(example))
                    self.fail(msg=message)
