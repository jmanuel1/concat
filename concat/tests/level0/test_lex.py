import concat.level0.lex as lex
import unittest
from typing import Tuple


TokenTuple = Tuple[str, str, Tuple[int, int], Tuple[int, int]]


class TestSmallExamples(unittest.TestCase):
    examples = {
        '$() $(0) bool\n': (  # newline is important
            ('ENCODING', 'utf-8', (0, 0), (0, 0)),
            ('DOLLARSIGN', '$', (1, 0), (1, 1)),
            ('LPAR', '(', (1, 1), (1, 2)),
            ('RPAR', ')', (1, 2), (1, 3)),
            ('DOLLARSIGN', '$', (1, 4), (1, 5)),
            ('LPAR', '(', (1, 5), (1, 6)),
            ('NUMBER', '0', (1, 6), (1, 7)),
            ('RPAR', ')', (1, 7), (1, 8)),
            ('NAME', 'bool', (1, 9), (1, 13)),
            ('NEWLINE', '\n', (1, 13), (1, 14)),
            ('ENDMARKER', '', (2, 0), (2, 0))
        ),
        "$() $('This is a string') len\n": (
            ('ENCODING', 'utf-8', (0, 0), (0, 0)),
            ('DOLLARSIGN', '$', (1, 0), (1, 1)),
            ('LPAR', '(', (1, 1), (1, 2)),
            ('RPAR', ')', (1, 2), (1, 3)),
            ('DOLLARSIGN', '$', (1, 4), (1, 5)),
            ('LPAR', '(', (1, 5), (1, 6)),
            ('STRING', "'This is a string'", (1, 6), (1, 24)),
            ('RPAR', ')', (1, 24), (1, 25)),
            ('NAME', 'len', (1, 26), (1, 29)),
            ('NEWLINE', '\n', (1, 29), (1, 30)),
            ('ENDMARKER', '', (2, 0), (2, 0))
        ),
        "$() $('Strings' 'interpolated') '{} can be {}'.format\n": (
            ('ENCODING', 'utf-8', (0, 0), (0, 0)),
            ('DOLLARSIGN', '$', (1, 0), (1, 1)),
            ('LPAR', '(', (1, 1), (1, 2)),
            ('RPAR', ')', (1, 2), (1, 3)),
            ('DOLLARSIGN', '$', (1, 4), (1, 5)),
            ('LPAR', '(', (1, 5), (1, 6)),
            ('STRING', "'Strings'", (1, 6), (1, 15)),
            ('STRING', "'interpolated'", (1, 16), (1, 30)),
            ('RPAR', ')', (1, 30), (1, 31)),
            ('STRING', "'{} can be {}'", (1, 32), (1, 46)),
            ('DOT', '.', (1, 46), (1, 47)),
            ('NAME', 'format', (1, 47), (1, 53)),
            ('NEWLINE', '\n', (1, 53), (1, 54)),
            ('ENDMARKER', '', (2, 0), (2, 0))
        )
    }

    def test_examples(self) -> None:
        for example in type(self).examples:
            with self.subTest(example=example):
                tokens = []
                lex.lexer.input(example)
                while True:
                    token = lex.lexer.token()
                    if token is None:
                        break
                    tokens.append(token)

                expectationPairs = zip(tokens, type(self).examples[example])
                self.assertTrue(
                    all(map(self._matches_token, expectationPairs)))

    def _matches_token(self, pair: Tuple[lex.Token, TokenTuple]) -> bool:
        token, tokTuple = pair

        return (
            token.type == tokTuple[0] and
            token.value == tokTuple[1] and
            token.start == tokTuple[2] and
            token.end == tokTuple[3]
        )
