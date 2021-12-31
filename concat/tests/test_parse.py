"""Test that the parser accepts valid token streams."""
import concat.parse
from concat.tests.small_example_programs import examples
import unittest
import parsy


class TestSmallExamples(unittest.TestCase):
    """Test that parser recognizes small example programs (token sequences)."""

    def test_examples(self) -> None:
        for example in examples:
            with self.subTest(example=example):
                tokens = examples[example]
                parsers = concat.parse.ParserDict()
                parsers.extend_with(concat.parse.extension)

                # We place a substitute stack effect parser in the dictionary
                parsers['stack-effect-type'] = (
                    parsers.token('NAME').many()
                    >> parsers.token('MINUS').many()
                    >> parsers.token('NAME').many()
                )

                # for example programs, we only test acceptance

                try:
                    parsers.parse(tuple(tokens))
                except parsy.ParseError:
                    message = '{} was not accepted by the parser'.format(
                        repr(example)
                    )
                    self.fail(msg=message)