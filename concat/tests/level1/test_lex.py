import concat.level1.lex as lex
import concat.level0.lex
import unittest
from typing import Tuple, Dict, Sequence


# TODO: Put token handling helpers in their own module.
TokenTuple = Tuple[str, str, Tuple[int, int], Tuple[int, int]]


class TestSmallExamples(unittest.TestCase):
    examples: Dict[str, Sequence[TokenTuple]] = {
        'None\n': (  # newline is important
            ('ENCODING', 'utf-8', (0, 0), (0, 0)),
            ('NONE', 'None', (1, 0), (1, 4)),
            ('NEWLINE', '\n', (1, 4), (1, 5)),
            ('ENDMARKER', '', (2, 0), (2, 0))
        ),
        'NotImplemented\n': (  # newline is important
            ('ENCODING', 'utf-8', (0, 0), (0, 0)),
            ('NOTIMPL', 'NotImplemented', (1, 0), (1, 14)),
            ('NEWLINE', '\n', (1, 14), (1, 15)),
            ('ENDMARKER', '', (2, 0), (2, 0))
        ),
        '... Ellipsis\n': (
            ('ENCODING', 'utf-8', (0, 0), (0, 0)),
            ('ELLIPSIS', '...', (1, 0), (1, 3)),
            ('ELLIPSIS', 'Ellipsis', (1, 4), (1, 12)),
            ('NEWLINE', '\n', (1, 12), (1, 13)),
            ('ENDMARKER', '', (2, 0), (2, 0))
        ),
        '[9]\n': (
            ('ENCODING', 'utf-8', (0, 0), (0, 0)),
            ('LSQB', '[', (1, 0), (1, 1)),
            ('NUMBER', '9', (1, 1), (1, 2)),
            ('RSQB', ']', (1, 2), (1, 3)),
            ('NEWLINE', '\n', (1, 3), (1, 4)),
            ('ENDMARKER', '', (2, 0), (2, 0))
        ),
        '[7:8]\n': (
            ('ENCODING', 'utf-8', (0, 0), (0, 0)),
            ('LSQB', '[', (1, 0), (1, 1)),
            ('NUMBER', '7', (1, 1), (1, 2)),
            ('COLON', ':', (1, 2), (1, 3)),
            ('NUMBER', '8', (1, 3), (1, 4)),
            ('RSQB', ']', (1, 4), (1, 5)),
            ('NEWLINE', '\n', (1, 5), (1, 6)),
            ('ENDMARKER', '', (2, 0), (2, 0))
        ),
        '[::0 1 -]\n': (
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
        "b'bytes'\n": (
            ('ENCODING', 'utf-8', (0, 0), (0, 0)),
            ('BYTES', "b'bytes'", (1, 0), (1, 8)),
            ('NEWLINE', '\n', (1, 8), (1, 9)),
            ('ENDMARKER', '', (2, 0), (2, 0))
        ),
        '(5,)\n': (
            ('ENCODING', 'utf-8', (0, 0), (0, 0)),
            ('LPAR', '(', (1, 0), (1, 1)),
            ('NUMBER', '5', (1, 1), (1, 2)),
            ('COMMA', ',', (1, 2), (1, 3)),
            ('RPAR', ')', (1, 3), (1, 4)),
            ('NEWLINE', '\n', (1, 4), (1, 5)),
            ('ENDMARKER', '', (2, 0), (2, 0))
        ),
        '[,]\n': (
            ('ENCODING', 'utf-8', (0, 0), (0, 0)),
            ('LSQB', '[', (1, 0), (1, 1)),
            ('COMMA', ',', (1, 1), (1, 2)),
            ('RSQB', ']', (1, 2), (1, 3)),
            ('NEWLINE', '\n', (1, 3), (1, 4)),
            ('ENDMARKER', '', (2, 0), (2, 0))
        ),
        'del .attr\n': (
            ('ENCODING', 'utf-8', (0, 0), (0, 0)),
            ('DEL', 'del', (1, 0), (1, 3)),
            ('DOT', '.', (1, 4), (1, 5)),
            ('NAME', 'attr', (1, 5), (1, 9)),
            ('NEWLINE', '\n', (1, 9), (1, 10)),
            ('ENDMARKER', '', (2, 0), (2, 0))
        ),
        'word yield\n': (
            ('ENCODING', 'utf-8', (0, 0), (0, 0)),
            ('NAME', 'word', (1, 0), (1, 4)),
            ('YIELD', 'yield', (1, 5), (1, 10)),
            ('NEWLINE', '\n', (1, 10), (1, 11)),
            ('ENDMARKER', '', (2, 0), (2, 0))
        ),
        'async def fun: 5\n': (
            ('ENCODING', 'utf-8', (0, 0), (0, 0)),
            ('ASYNC', 'async', (1, 0), (1, 5)),
            ('DEF', 'def', (1, 6), (1, 9)),
            ('NAME', 'fun', (1, 10), (1, 13)),
            ('COLON', ':', (1, 13), (1, 14)),
            ('NUMBER', '5', (1, 15), (1, 16)),
            ('NEWLINE', '\n', (1, 16), (1, 17)),
            ('ENDMARKER', '', (2, 0), (2, 0))
        ),
        'word await\n': (
            ('ENCODING', 'utf-8', (0, 0), (0, 0)),
            ('NAME', 'word', (1, 0), (1, 4)),
            ('AWAIT', 'await', (1, 5), (1, 10)),
            ('NEWLINE', '\n', (1, 10), (1, 11)),
            ('ENDMARKER', '', (2, 0), (2, 0))
        )
    }

    def test_examples(self) -> None:
        for example in self.examples:
            with self.subTest(example=example):
                tokens = []
                lex.lexer.input(example)
                while True:
                    token = lex.lexer.token()
                    if token is None:
                        break
                    tokens.append(token)

                expectationPairs = zip(tokens, self.examples[example])
                self.assertTrue(
                    all(map(self._matches_token, expectationPairs)))

    def _matches_token(
        self,
        pair: Tuple[concat.level0.lex.Token, TokenTuple]
    ) -> bool:
        token, tokTuple = pair

        return (
            token.type == tokTuple[0]
            and token.value == tokTuple[1]
            and token.start == tokTuple[2]
            and token.end == tokTuple[3]
        )
