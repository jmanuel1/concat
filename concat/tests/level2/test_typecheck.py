import concat.lex as lex
import concat.level0.parse
import concat.level1.parse
import concat.level1.typecheck
from concat.level1.typecheck.types import (
    IndividualVariable,
    _IntersectionType,
    StackEffect,
    ObjectType,
    object_type,
)
import concat.level2.typecheck
import concat.level2.preamble_types
import concat.level2.parse
import concat.astutils
import unittest
from textwrap import dedent
from typing import List, Dict, cast
import parsy
from hypothesis import given, example, note
from hypothesis.strategies import from_type


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

    def test_function_with_strict_effect(self) -> None:
        """Test that a function type checks with a strict annotated effect.

        The type checker should allow the annotated effect of a function to be
        stricter than what would be inferred without the annotation."""
        tree = parse(
            dedent(
                """\
            def seek_file(file:file offset:int whence:int --):
                swap [(), (),] [,] swap pick $.seek py_call drop drop
        """
            )
        )
        env = concat.level1.typecheck.Environment(
            # FIXME: These ought to be combined.
            {
                **concat.level2.preamble_types.types,
                **concat.level2.typecheck.builtin_environment,
            }
        )
        concat.level1.typecheck.infer(
            env, tree.children, (concat.level2.typecheck.infer,), True
        )
        # If we get here, we passed

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
        tree = parse('$[0] cast (int) 1 +')
        concat.level1.typecheck.infer(
            concat.level2.typecheck.builtin_environment,
            tree.children,
            (concat.level2.typecheck.infer,),
        )


class TestStackEffectParser(unittest.TestCase):
    _a_bar = concat.level1.typecheck.SequenceVariable()
    _d_bar = concat.level1.typecheck.SequenceVariable()
    _b = concat.level1.typecheck.IndividualVariable()
    _c = concat.level1.typecheck.IndividualVariable()
    examples: Dict[str, StackEffect] = {
        'a b -- b a': StackEffect([_a_bar, _b, _c], [_a_bar, _c, _b]),
        'a -- a a': StackEffect([_a_bar, _b], [_a_bar, _b, _b]),
        'a --': StackEffect([_a_bar, _b], [_a_bar]),
        'a:object b:object -- b a': StackEffect(
            [_a_bar, object_type, object_type,], [_a_bar, *[object_type] * 2],
        ),
        'a:`t -- a a': StackEffect([_a_bar, _b], [_a_bar, _b, _b]),
        '*i -- *i a': StackEffect([_a_bar], [_a_bar, _b]),
        '*i fun:(*i -- *o) -- *o': StackEffect(
            [_a_bar, StackEffect([_a_bar], [_d_bar])], [_d_bar],
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
                env = concat.level2.typecheck.builtin_environment
                self.assertEqual(
                    effect.to_type(env)[0], self.examples[example],
                )


class TestNamedTypeNode(unittest.TestCase):
    @given(from_type(concat.level2.typecheck.NamedTypeNode))
    def test_name_does_not_exist(self, named_type_node):
        self.assertRaises(
            concat.level1.typecheck.NameError,
            named_type_node.to_type,
            concat.level1.typecheck.Environment(),
        )

    def test_builtin_name_does_not_exist_in_empty_environment(self):
        named_type_node = concat.level2.typecheck.NamedTypeNode((0, 0), 'int')
        self.assertRaises(
            concat.level1.typecheck.NameError,
            named_type_node.to_type,
            concat.level1.typecheck.Environment(),
        )

    @given(
        from_type(concat.level2.typecheck.NamedTypeNode),
        from_type(concat.level1.typecheck.IndividualType),
    )
    @example(
        named_type_node=concat.level2.typecheck.NamedTypeNode((0, 0), ''),
        type=StackEffect(
            (),
            ((_IntersectionType(StackEffect((), ()), StackEffect((), ()),)),),
        ),
    )
    @example(
        named_type_node=concat.level2.typecheck.NamedTypeNode((0, 0), ''),
        type=IndividualVariable(),
    )
    @example(
        named_type_node=concat.level2.typecheck.NamedTypeNode((0, 0), ''),
        type=StackEffect(
            (),
            (
                (
                    IndividualVariable()
                    & (
                        ObjectType(IndividualVariable(), {}, (), [], False)
                        & IndividualVariable()
                    )
                ),
            ),
        ),
    )
    def test_name_does_exist(self, named_type_node, type):
        env = concat.level1.typecheck.Environment({named_type_node.name: type})
        expected_type = named_type_node.to_type(env)[0]
        note((expected_type, type))
        self.assertEqual(named_type_node.to_type(env)[0], type)
