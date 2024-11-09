import concat.lex as lex
from concat.tests.small_example_programs import examples
import textwrap
import unittest


class TestSmallExamples(unittest.TestCase):
    def test_examples(self) -> None:
        all_examples = {
            '`': lex.to_tokens(
                ('ENCODING', 'utf-8', (0, 0), (0, 0)),
                ('BACKTICK', '`', (1, 0), (1, 1)),
                ('NEWLINE', '', (1, 1), (1, 2)),
                ('ENDMARKER', '', (2, 0), (2, 0)),
            ),
            '!': lex.to_tokens(
                ('ENCODING', 'utf-8', (0, 0), (0, 0)),
                ('EXCLAMATIONMARK', '!', (1, 0), (1, 1)),
                ('NEWLINE', '', (1, 1), (1, 2)),
                ('ENDMARKER', '', (2, 0), (2, 0)),
            ),
            **examples,
        }
        for example, expected_tokens in all_examples.items():
            with self.subTest(example=example):
                tokens = []
                lexer = lex.Lexer()
                lexer.input(example)
                while True:
                    token = lexer.token()
                    if token is None:
                        break
                    tokens.append(token)

                self.assertEqual(len(tokens), len(expected_tokens))
                expectationPairs = zip(
                    tokens, map(lex.TokenResult, expected_tokens)
                )
                for actual_token, expected_token in expectationPairs:
                    self.assertEqual(actual_token, expected_token)

    def test_indentation_error(self) -> None:
        code = textwrap.dedent("""\
            def remove_stack_polymorphism(
                f:forall `t *s. (*s i:`t -- *s) -- g:forall `t. (i:`t -- )
            ):
              ()
             dfbfdbff""")
        lexer = lex.Lexer()
        lexer.input(code)
        while True:
            token = lexer.token()
            if token is None:
                break
