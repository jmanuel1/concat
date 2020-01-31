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
        ),
        '(5,)\n': to_tokens(
            ('ENCODING', 'utf-8', (0, 0), (0, 0)),
            ('LPAR', '(', (1, 0), (1, 1)),
            ('NUMBER', '5', (1, 1), (1, 2)),
            ('COMMA', ',', (1, 2), (1, 3)),
            ('RPAR', ')', (1, 3), (1, 4)),
            ('NEWLINE', '\n', (1, 4), (1, 5)),
            ('ENDMARKER', '', (2, 0), (2, 0))
        ),
        '[,]\n': to_tokens(
            ('ENCODING', 'utf-8', (0, 0), (0, 0)),
            ('LSQB', '[', (1, 0), (1, 1)),
            ('COMMA', ',', (1, 1), (1, 2)),
            ('RSQB', ']', (1, 2), (1, 3)),
            ('NEWLINE', '\n', (1, 3), (1, 4)),
            ('ENDMARKER', '', (2, 0), (2, 0))
        ),
        '(1,2,3)\n': to_tokens(
            ('ENCODING', 'utf-8', (0, 0), (0, 0)),
            ('LPAR', '(', (1, 0), (1, 1)),
            ('NUMBER', '1', (1, 1), (1, 2)),
            ('COMMA', ',', (1, 2), (1, 3)),
            ('NUMBER', '2', (1, 3), (1, 4)),
            ('COMMA', ',', (1, 4), (1, 5)),
            ('NUMBER', '3', (1, 5), (1, 6)),
            ('RPAR', ')', (1, 6), (1, 7)),
            ('NEWLINE', '\n', (1, 7), (1, 8)),
            ('ENDMARKER', '', (2, 0), (2, 0))
        ),
        '(1,2,)\n': to_tokens(
            ('ENCODING', 'utf-8', (0, 0), (0, 0)),
            ('LPAR', '(', (1, 0), (1, 1)),
            ('NUMBER', '1', (1, 1), (1, 2)),
            ('COMMA', ',', (1, 2), (1, 3)),
            ('NUMBER', '2', (1, 3), (1, 4)),
            ('COMMA', ',', (1, 4), (1, 5)),
            ('RPAR', ')', (1, 5), (1, 6)),
            ('NEWLINE', '\n', (1, 6), (1, 7)),
            ('ENDMARKER', '', (2, 0), (2, 0))
        ),
        'del .attr\n': to_tokens(
            ('ENCODING', 'utf-8', (0, 0), (0, 0)),
            ('DEL', 'del', (1, 0), (1, 3)),
            ('DOT', '.', (1, 4), (1, 5)),
            ('NAME', 'attr', (1, 5), (1, 9)),
            ('NEWLINE', '\n', (1, 9), (1, 10)),
            ('ENDMARKER', '', (2, 0), (2, 0))
        ),
        '{1,2,3,}\n': to_tokens(
            ('ENCODING', 'utf-8', (0, 0), (0, 0)),
            ('LBRACE', '{', (1, 0), (1, 1)),
            ('NUMBER', '1', (1, 1), (1, 2)),
            ('COMMA', ',', (1, 2), (1, 3)),
            ('NUMBER', '2', (1, 3), (1, 4)),
            ('COMMA', ',', (1, 4), (1, 5)),
            ('NUMBER', '3', (1, 5), (1, 6)),
            ('COMMA', ',', (1, 6), (1, 7)),
            ('RBRACE', '}', (1, 7), (1, 8)),
            ('NEWLINE', '\n', (1, 8), (1, 9)),
            ('ENDMARKER', '', (2, 0), (2, 0))
        ),
        "{'a':1,'b':2}\n": to_tokens(
            ('ENCODING', 'utf-8', (0, 0), (0, 0)),
            ('LBRACE', '{', (1, 0), (1, 1)),
            ('STRING', "'a'", (1, 1), (1, 4)),
            ('COLON', ':', (1, 4), (1, 5)),
            ('NUMBER', '1', (1, 5), (1, 6)),
            ('COMMA', ',', (1, 6), (1, 7)),
            ('STRING', "'b'", (1, 7), (1, 10)),
            ('COLON', ':', (1, 10), (1, 11)),
            ('NUMBER', '2', (1, 11), (1, 12)),
            ('RBRACE', '}', (1, 12), (1, 13)),
            ('NEWLINE', '\n', (1, 13), (1, 14)),
            ('ENDMARKER', '', (2, 0), (2, 0))
        ),
        'word yield\n': to_tokens(
            ('ENCODING', 'utf-8', (0, 0), (0, 0)),
            ('NAME', 'word', (1, 0), (1, 4)),
            ('YIELD', 'yield', (1, 5), (1, 10)),
            ('NEWLINE', '\n', (1, 10), (1, 11)),
            ('ENDMARKER', '', (2, 0), (2, 0))
        ),
        'async def fun: 5\n': to_tokens(
            ('ENCODING', 'utf-8', (0, 0), (0, 0)),
            ('ASYNC', 'async', (1, 0), (1, 5)),
            ('DEF', 'def', (1, 6), (1, 9)),
            ('NAME', 'fun', (1, 10), (1, 13)),
            ('COLON', ':', (1, 13), (1, 14)),
            ('NUMBER', '5', (1, 15), (1, 16)),
            ('NEWLINE', '\n', (1, 16), (1, 17)),
            ('ENDMARKER', '', (2, 0), (2, 0))
        ),
        'word await\n': to_tokens(
            ('ENCODING', 'utf-8', (0, 0), (0, 0)),
            ('NAME', 'word', (1, 0), (1, 4)),
            ('AWAIT', 'await', (1, 5), (1, 10)),
            ('NEWLINE', '\n', (1, 10), (1, 11)),
            ('ENDMARKER', '', (2, 0), (2, 0))
        ),
        'import a.submodule\n': to_tokens(
            ('ENCODING', 'utf-8', (0, 0), (0, 0)),
            ('IMPORT', 'import', (1, 0), (1, 6)),
            ('NAME', 'a', (1, 7), (1, 8)),
            ('DOT', '.', (1, 8), (1, 9)),
            ('NAME', 'submodule', (1, 9), (1, 18)),
            ('NEWLINE', '\n', (1, 18), (1, 19)),
            ('ENDMARKER', '', (2, 0), (2, 0))
        ),
        'import a as b\n': to_tokens(
            ('ENCODING', 'utf-8', (0, 0), (0, 0)),
            ('IMPORT', 'import', (1, 0), (1, 6)),
            ('NAME', 'a', (1, 7), (1, 8)),
            ('AS', 'as', (1, 9), (1, 11)),
            ('NAME', 'b', (1, 12), (1, 13)),
            ('NEWLINE', '\n', (1, 13), (1, 14)),
            ('ENDMARKER', '', (2, 0), (2, 0))
        ),
        'from .a import b\n': to_tokens(
            ('ENCODING', 'utf-8', (0, 0), (0, 0)),
            ('FROM', 'from', (1, 0), (1, 4)),
            ('DOT', '.', (1, 5), (1, 6)),
            ('NAME', 'a', (1, 6), (1, 7)),
            ('IMPORT', 'import', (1, 8), (1, 14)),
            ('NAME', 'b', (1, 15), (1, 16)),
            ('NEWLINE', '\n', (1, 16), (1, 17)),
            ('ENDMARKER', '', (2, 0), (2, 0))
        ),
        'from .a import b as c\n': to_tokens(
            ('ENCODING', 'utf-8', (0, 0), (0, 0)),
            ('FROM', 'from', (1, 0), (1, 4)),
            ('DOT', '.', (1, 5), (1, 6)),
            ('NAME', 'a', (1, 6), (1, 7)),
            ('IMPORT', 'import', (1, 8), (1, 14)),
            ('NAME', 'b', (1, 15), (1, 16)),
            ('AS', 'as', (1, 17), (1, 19)),
            ('NAME', 'c', (1, 20), (1, 21)),
            ('NEWLINE', '\n', (1, 21), (1, 22)),
            ('ENDMARKER', '', (2, 0), (2, 0))
        ),
        'from a import *\n': to_tokens(
            ('ENCODING', 'utf-8', (0, 0), (0, 0)),
            ('FROM', 'from', (1, 0), (1, 4)),
            ('NAME', 'a', (1, 5), (1, 6)),
            ('IMPORT', 'import', (1, 7), (1, 13)),
            ('STAR', '*', (1, 14), (1, 15)),
            ('NEWLINE', '\n', (1, 15), (1, 16)),
            ('ENDMARKER', '', (2, 0), (2, 0))
        ),
        'class A: pass\n': to_tokens(
            ('ENCODING', 'utf-8', (0, 0), (0, 0)),
            ('CLASS', 'class', (1, 0), (1, 5)),
            ('NAME', 'A', (1, 6), (1, 7)),
            ('COLON', ':', (1, 7), (1, 8)),
            ('NAME', 'pass', (1, 9), (1, 13)),
            ('NEWLINE', '\n', (1, 13), (1, 14)),
            ('ENDMARKER', '', (2, 0), (2, 0))
        ),
        'class A @decorator: pass\n': to_tokens(
            ('ENCODING', 'utf-8', (0, 0), (0, 0)),
            ('CLASS', 'class', (1, 0), (1, 5)),
            ('NAME', 'A', (1, 6), (1, 7)),
            ('AT', '@', (1, 8), (1, 9)),
            ('NAME', 'decorator', (1, 9), (1, 18)),
            ('COLON', ':', (1, 18), (1, 19)),
            ('NAME', 'pass', (1, 20), (1, 24)),
            ('NEWLINE', '\n', (1, 24), (1, 25)),
            ('ENDMARKER', '', (2, 0), (2, 0))
        ),
        'class A($B,): pass\n': to_tokens(
            ('ENCODING', 'utf-8', (0, 0), (0, 0)),
            ('CLASS', 'class', (1, 0), (1, 5)),
            ('NAME', 'A', (1, 6), (1, 7)),
            ('LPAR', '(', (1, 7), (1, 8)),
            ('DOLLARSIGN', '$', (1, 8), (1, 9)),
            ('NAME', 'B', (1, 9), (1, 10)),
            ('COMMA', ',', (1, 10), (1, 11)),
            ('RPAR', ')', (1, 11), (1, 12)),
            ('COLON', ':', (1, 12), (1, 13)),
            ('NAME', 'pass', (1, 14), (1, 18)),
            ('NEWLINE', '\n', (1, 18), (1, 19)),
            ('ENDMARKER', '', (2, 0), (2, 0))
        ),
        'def test: pass\n': to_tokens(
            ('ENCODING', 'utf-8', (0, 0), (0, 0)),
            ('DEF', 'def', (1, 0), (1, 3)),
            ('NAME', 'test', (1, 4), (1, 8)),
            ('COLON', ':', (1, 8), (1, 9)),
            ('NAME', 'pass', (1, 10), (1, 14)),
            ('NEWLINE', '\n', (1, 14), (1, 15)),
            ('ENDMARKER', '', (2, 0), (2, 0))
        ),
        'class A metaclass=$M: pass\n': to_tokens(
            ('ENCODING', 'utf-8', (0, 0), (0, 0)),
            ('CLASS', 'class', (1, 0), (1, 5)),
            ('NAME', 'A', (1, 6), (1, 7)),
            ('NAME', 'metaclass', (1, 8), (1, 17)),
            ('EQUAL', '=', (1, 17), (1, 18)),
            ('DOLLARSIGN', '$', (1, 18), (1, 19)),
            ('NAME', 'M', (1, 19), (1, 20)),
            ('COLON', ':', (1, 20), (1, 21)),
            ('NAME', 'pass', (1, 22), (1, 26)),
            ('NEWLINE', '\n', (1, 26), (1, 27)),
            ('ENDMARKER', '', (2, 0), (2, 0))
        ),
        '2 4 **\n': to_tokens(
            ('ENCODING', 'utf-8', (0, 0), (0, 0)),
            ('NUMBER', '2', (1, 0), (1, 1)),
            ('NUMBER', '4', (1, 2), (1, 3)),
            ('DOUBLESTAR', '**', (1, 4), (1, 6)),
            ('NEWLINE', '\n', (1, 6), (1, 7)),
            ('ENDMARKER', '', (2, 0), (2, 0))
        ),
        '0 ~\n': to_tokens(
            ('ENCODING', 'utf-8', (0, 0), (0, 0)),
            ('NUMBER', '0', (1, 0), (1, 1)),
            ('TILDE', '~', (1, 2), (1, 3)),
            ('NEWLINE', '\n', (1, 3), (1, 4)),
            ('ENDMARKER', '', (2, 0), (2, 0))
        ),
        '6 9 *\n': to_tokens(
            ('ENCODING', 'utf-8', (0, 0), (0, 0)),
            ('NUMBER', '6', (1, 0), (1, 1)),
            ('NUMBER', '9', (1, 2), (1, 3)),
            ('STAR', '*', (1, 4), (1, 5)),
            ('NEWLINE', '\n', (1, 5), (1, 6)),
            ('ENDMARKER', '', (2, 0), (2, 0))
        ),
        'A B @\n': to_tokens(
            ('ENCODING', 'utf-8', (0, 0), (0, 0)),
            ('NAME', 'A', (1, 0), (1, 1)),
            ('NAME', 'B', (1, 2), (1, 3)),
            ('AT', '@', (1, 4), (1, 5)),
            ('NEWLINE', '\n', (1, 5), (1, 6)),
            ('ENDMARKER', '', (2, 0), (2, 0))
        ),
        '1 2 //\n': to_tokens(
            ('ENCODING', 'utf-8', (0, 0), (0, 0)),
            ('NUMBER', '1', (1, 0), (1, 1)),
            ('NUMBER', '2', (1, 2), (1, 3)),
            ('DOUBLESLASH', '//', (1, 4), (1, 6)),
            ('NEWLINE', '\n', (1, 6), (1, 7)),
            ('ENDMARKER', '', (2, 0), (2, 0))
        ),
        '1 2 /\n': to_tokens(
            ('ENCODING', 'utf-8', (0, 0), (0, 0)),
            ('NUMBER', '1', (1, 0), (1, 1)),
            ('NUMBER', '2', (1, 2), (1, 3)),
            ('SLASH', '/', (1, 4), (1, 5)),
            ('NEWLINE', '\n', (1, 5), (1, 6)),
            ('ENDMARKER', '', (2, 0), (2, 0))
        ),
        '1 2 %\n': to_tokens(
            ('ENCODING', 'utf-8', (0, 0), (0, 0)),
            ('NUMBER', '1', (1, 0), (1, 1)),
            ('NUMBER', '2', (1, 2), (1, 3)),
            ('PERCENT', '%', (1, 4), (1, 5)),
            ('NEWLINE', '\n', (1, 5), (1, 6)),
            ('ENDMARKER', '', (2, 0), (2, 0))
        ),
        '1 2 +\n': to_tokens(
            ('ENCODING', 'utf-8', (0, 0), (0, 0)),
            ('NUMBER', '1', (1, 0), (1, 1)),
            ('NUMBER', '2', (1, 2), (1, 3)),
            ('PLUS', '+', (1, 4), (1, 5)),
            ('NEWLINE', '\n', (1, 5), (1, 6)),
            ('ENDMARKER', '', (2, 0), (2, 0))
        ),
        '1 2 -\n': to_tokens(
            ('ENCODING', 'utf-8', (0, 0), (0, 0)),
            ('NUMBER', '1', (1, 0), (1, 1)),
            ('NUMBER', '2', (1, 2), (1, 3)),
            ('MINUS', '-', (1, 4), (1, 5)),
            ('NEWLINE', '\n', (1, 5), (1, 6)),
            ('ENDMARKER', '', (2, 0), (2, 0))
        ),
        '1 2 <<\n': to_tokens(
            ('ENCODING', 'utf-8', (0, 0), (0, 0)),
            ('NUMBER', '1', (1, 0), (1, 1)),
            ('NUMBER', '2', (1, 2), (1, 3)),
            ('LEFTSHIFT', '<<', (1, 4), (1, 6)),
            ('NEWLINE', '\n', (1, 6), (1, 7)),
            ('ENDMARKER', '', (2, 0), (2, 0))
        ),
        '1 2 >>\n': to_tokens(
            ('ENCODING', 'utf-8', (0, 0), (0, 0)),
            ('NUMBER', '1', (1, 0), (1, 1)),
            ('NUMBER', '2', (1, 2), (1, 3)),
            ('RIGHTSHIFT', '>>', (1, 4), (1, 6)),
            ('NEWLINE', '\n', (1, 6), (1, 7)),
            ('ENDMARKER', '', (2, 0), (2, 0))
        )
    }

    def test_examples(self) -> None:
        for example in self.examples:
            with self.subTest(example=example):
                tokens = self.examples[example]
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
