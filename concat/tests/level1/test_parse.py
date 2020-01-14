"""Tests that the level 1 parser accepts valid level 1 token streams."""
import concat.level0.parse
import concat.level1.parse
from concat.level0.lex import Token
import unittest
from typing import Tuple, Iterable
import parsy


TokenTuple = Tuple[str, str, Tuple[int, int], Tuple[int, int]]


def to_token(tupl: TokenTuple) -> Token:
    """Make a Token object out of tuple."""
    token = Token()
    token.type, token.value, token.start, token.end = tupl
    return token


def to_tokens(*tokTuples: TokenTuple) -> Iterable[Token]:
    """Make an iterable of Token objects out of the arguments of tuples."""
    for tupl in tokTuples:
        yield to_token(tupl)


class TestSmallExamples(unittest.TestCase):
    """Test that parser recognizes small example programs (token sequences)."""
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
        ),
        '... Ellipsis\n': to_tokens(
            ('ENCODING', 'utf-8', (0, 0), (0, 0)),
            ('ELLIPSIS', '...', (1, 0), (1, 3)),
            ('ELLIPSIS', 'Ellipsis', (1, 4), (1, 12)),
            ('NEWLINE', '\n', (1, 12), (1, 13)),
            ('ENDMARKER', '', (2, 0), (2, 0))
        ),
        '[9]\n': to_tokens(
            ('ENCODING', 'utf-8', (0, 0), (0, 0)),
            ('LSQB', '[', (1, 0), (1, 1)),
            ('NUMBER', '9', (1, 1), (1, 2)),
            ('RSQB', ']', (1, 2), (1, 3)),
            ('NEWLINE', '\n', (1, 3), (1, 4)),
            ('ENDMARKER', '', (2, 0), (2, 0))
        ),
        '[7:8]\n': to_tokens(
            ('ENCODING', 'utf-8', (0, 0), (0, 0)),
            ('LSQB', '[', (1, 0), (1, 1)),
            ('NUMBER', '7', (1, 1), (1, 2)),
            ('COLON', ':', (1, 2), (1, 3)),
            ('NUMBER', '8', (1, 3), (1, 4)),
            ('RSQB', ']', (1, 4), (1, 5)),
            ('NEWLINE', '\n', (1, 5), (1, 6)),
            ('ENDMARKER', '', (2, 0), (2, 0))
        ),
        '[::0 1 -]\n': to_tokens(
            ('ENCODING', 'utf-8', (0, 0), (0, 0)),
            ('LSQB', '[', (1, 0), (1, 1)),
            ('COLON', ':', (1, 1), (1, 2)),
            ('COLON', ':', (1, 2), (1, 3)),
            ('NUMBER', '0', (1, 3), (1, 4)),
            ('NUMBER', '1', (1, 5), (1, 6)),
            ('MINUS', '-', (1, 7), (1, 8)),
            ('RSQB', ']', (1, 8), (1, 9)),
            ('NEWLINE', '\n', (1, 9), (1, 10)),
            ('ENDMARKER', '', (2, 0), (2, 0))
        ),
        "b'bytes'\n": to_tokens(
            ('ENCODING', 'utf-8', (0, 0), (0, 0)),
            ('BYTES', "b'bytes'", (1, 0), (1, 8)),
            ('NEWLINE', '\n', (1, 8), (1, 9)),
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
