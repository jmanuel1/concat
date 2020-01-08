import concat.level1.lex as lex
import concat.level0.lex
import unittest
from typing import Tuple


# TODO: Put token handling helpers in their own module.
TokenTuple = Tuple[str, str, Tuple[int, int], Tuple[int, int]]


class TestSmallExamples(unittest.TestCase):
    examples = {
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
