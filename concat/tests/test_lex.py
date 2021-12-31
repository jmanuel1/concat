import concat.lex as lex
from concat.lex import TokenTuple
from concat.tests.small_example_programs import examples
import unittest
from typing import Tuple, Dict, Sequence


class TestSmallExamples(unittest.TestCase):
    def test_examples(self) -> None:
        for example in examples:
            with self.subTest(example=example):
                tokens = []
                lexer = lex.Lexer()
                lexer.input(example)
                while True:
                    token = lexer.token()
                    if token is None:
                        break
                    tokens.append(token)

                expectationPairs = zip(tokens, examples[example])
                self.assertTrue(
                    all(map(self._matches_token, expectationPairs))
                )

    def _matches_token(self, pair: Tuple[lex.Token, lex.Token]) -> bool:
        return pair[0] == pair[1]
