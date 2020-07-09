import concat.lex as lex
import concat.level0.parse
import concat.level1.parse
import concat.level1.typecheck
import concat.level2.typecheck
import concat.level2.parse
import concat.astutils
import unittest
from typing import List, Iterable, Type, Tuple, Dict, cast
import parsy


def lex_string(string: str) -> List[concat.level0.lex.Token]:
    return lex.tokenize(string)


def parse(string: str) -> concat.level0.parse.TopLevelNode:
    tokens = lex_string(string)
    parsers = build_parsers()
    tree = cast(concat.level0.parse.TopLevelNode, parsers.parse(tokens))
    return tree


def build_parsers() -> concat.level0.parse.ParserDict:
    parsers = concat.level0.parse.ParserDict()
    parsers.extend_with(concat.level0.parse.level_0_extension)
    parsers.extend_with(concat.level1.parse.level_1_extension)
    parsers.extend_with(concat.level2.typecheck.typecheck_extension)
    parsers.extend_with(concat.level2.parse.level_2_extension)
    return parsers


class TestTypeChecker(unittest.TestCase):
    def test_function_with_stack_effect(self) -> None:
        funcdef = 'def f(a b -- c): ()\n'
        tree = parse(funcdef)
        self.assertRaises(
            concat.level1.typecheck.TypeError,
            concat.level1.typecheck.infer,
            concat.level1.typecheck.Environment(),
            tree.children,
            (concat.level2.typecheck.infer,),
            True,
        )

    def test_string_subscription(self) -> None:
        """Test that the type checker allows subscription into strings."""
        tree = parse('"a string" [1]')
        concat.level1.typecheck.infer(
            concat.level1.typecheck.Environment(),
            tree.children,
            (concat.level2.typecheck.infer,),
            True,
        )

    def test_list_subscription(self) -> None:
        """Test that the type checker allows subscription into lists."""
        tree = parse('["a string", "another string",] [1]')
        concat.level1.typecheck.infer(
            concat.level1.typecheck.Environment(),
            tree.children,
            (concat.level2.typecheck.infer,),
            True,
        )

    def test_pushed_subscription(self) -> None:
        """Test that the type checker allows pushed subscription words."""
        tree = parse('$[0] cast (int) 1 -')
        concat.level1.typecheck.infer(
            concat.level1.typecheck.Environment(),
            tree.children,
            (concat.level2.typecheck.infer,),
        )


class TestStackEffectParser(unittest.TestCase):
    _a_bar = concat.level1.typecheck.SequenceVariable()
    _d_bar = concat.level1.typecheck.SequenceVariable()
    _b = concat.level1.typecheck.IndividualVariable()
    _c = concat.level1.typecheck.IndividualVariable()
    examples: Dict[str, concat.level1.typecheck.StackEffect] = {
        'a b -- b a': concat.level1.typecheck.StackEffect(
            [_a_bar, _b, _c], [_a_bar, _c, _b]
        ),
        'a -- a a': concat.level1.typecheck.StackEffect(
            [_a_bar, _b], [_a_bar, _b, _b]
        ),
        'a --': concat.level1.typecheck.StackEffect([_a_bar, _b], [_a_bar]),
        'a:object b:object -- b a': concat.level1.typecheck.StackEffect(
            [
                _a_bar,
                concat.level1.typecheck.PrimitiveTypes.object,
                concat.level1.typecheck.PrimitiveTypes.object,
            ],
            [_a_bar, *[concat.level1.typecheck.PrimitiveTypes.object] * 2],
        ),
        'a:`t -- a a': concat.level1.typecheck.StackEffect(
            [_a_bar, _b], [_a_bar, _b, _b]
        ),
        '*i -- *i a': concat.level1.typecheck.StackEffect(
            [_a_bar], [_a_bar, _b]
        ),
        '*i fun:(*i -- *o) -- *o': concat.level1.typecheck.StackEffect(
            [_a_bar, concat.level1.typecheck.StackEffect([_a_bar], [_d_bar])],
            [_d_bar],
        ),
    }

    def test_examples(self) -> None:
        for example in self.examples:
            with self.subTest(example=example):
                tokens = lex_string(example)
                # exclude ENCODING, NEWLINE and ENDMARKER
                tokens = tokens[1:-2]
                try:
                    effect = build_parsers()['stack-effect-type'].parse(tokens)
                except parsy.ParseError as e:
                    self.fail('could not parse {}\n{}'.format(example, e))
                subs = concat.level1.typecheck.Substitutions()
                env = concat.level1.typecheck.Environment()
                self.assertEqual(
                    concat.level2.typecheck.ast_to_type(effect, subs, env)[0],
                    self.examples[example],
                )
