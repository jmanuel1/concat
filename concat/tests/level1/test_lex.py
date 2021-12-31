import concat.level1.lex as lex
from concat.tests.small_example_programs import examples
import unittest


class TestSmallExamples(unittest.TestCase):
    def test_examples(self) -> None:
        for example in examples:
            with self.subTest(example=example):
                tokens = []
                lex.lexer.input(example)
                while True:
                    token = lex.lexer.token()
                    if token is None:
                        break
                    tokens.append(token)

                message = '{!r} is not lexed correctly'.format(example)
                self.assertEqual(tokens, [*examples[example]], message)
