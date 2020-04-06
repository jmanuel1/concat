import concat.level0.parse as parse
from concat.level0.lex import to_tokens
import unittest
import parsy


class TestSmallExamples(unittest.TestCase):
    examples = {
        '$() $(0) bool\n': to_tokens(  # newline is important
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
        "$() $('This is a string') len\n": to_tokens(
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
        "$() $('Strings' 'interpolated') '{} can be {}'.format\n": to_tokens(
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
                tokens = type(self).examples[example]
                parsers = parse.ParserDict()
                parsers.extend_with(parse.level_0_extension)

                # for example programs, we only test acceptance

                try:
                    parsers.parse(tuple(tokens))
                except parsy.ParseError:
                    message = '{} was not accepted by the parser'.format(
                        example)
                    self.fail(msg=message)
