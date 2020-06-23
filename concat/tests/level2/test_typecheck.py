import concat.lex as lex
import concat.level0.parse
import concat.level1.parse
import concat.level1.typecheck
import concat.level2.typecheck
import concat.level2.parse
import concat.astutils
import unittest
from typing import List, Iterable, Type, Tuple, Dict, cast
from hypothesis.strategies import (SearchStrategy, text, lists, builds,  # type: ignore
                                   from_type, one_of, register_type_strategy,
                                   just, integers, iterables,
                                   binary)
from hypothesis import given, infer  # type: ignore
import parsy


def register_builds_strategy(
    type: Type[object],
    *strategies: SearchStrategy,
    **k_strategies: SearchStrategy
) -> None:
    strategy = builds(type, *strategies, **k_strategies)
    register_type_strategy(type, strategy)

# Strategy for generating type-correct programs


del_statement_node = builds(concat.level1.parse.DelStatementNode,
                            lists(from_type(concat.level0.parse.WordNode),
                                  min_size=1))
register_type_strategy(concat.level1.parse.DelStatementNode,
                       del_statement_node)

register_type_strategy(Iterable[concat.level0.parse.WordNode], iterables(
    from_type(concat.level0.parse.WordNode)))

register_type_strategy(Iterable[concat.astutils.Words], iterables(
    from_type(concat.astutils.Words)))

register_type_strategy(Iterable[Iterable[concat.level0.parse.WordNode]], iterables(
    from_type(Iterable[concat.level0.parse.WordNode])))

register_type_strategy(Iterable[Iterable[List[concat.level0.parse.WordNode]]], iterables(
    from_type(Iterable[List[concat.level0.parse.WordNode]])))

number_word_node = builds(concat.level0.parse.NumberWordNode,
                          builds(concat.level0.lex.Token, text(), integers().map(repr), start=infer, end=infer))
register_type_strategy(concat.level0.parse.NumberWordNode, number_word_node)

string_word_node = builds(concat.level0.parse.StringWordNode,
                          builds(concat.level0.lex.Token, text(), text().map(repr), start=infer, end=infer))
register_type_strategy(concat.level0.parse.StringWordNode, string_word_node)

slice_word_node = builds(concat.level1.parse.SliceWordNode,
                         iterables(from_type(Iterable[concat.level0.parse.WordNode]), min_size=3, max_size=3))
register_type_strategy(concat.level1.parse.SliceWordNode, slice_word_node)

bytes_word_node = builds(concat.level1.parse.BytesWordNode,
                         builds(concat.level0.lex.Token, text(), binary().map(repr), start=infer, end=infer))
register_type_strategy(concat.level1.parse.BytesWordNode, bytes_word_node)

register_builds_strategy(concat.level1.parse.DictWordNode, iterables(iterables(
    from_type(concat.astutils.Words), min_size=2, max_size=2)), location=infer)

attr_type_node = builds(concat.level2.typecheck.AttributeTypeNode,
                        location=infer, name=text(), type=from_type(concat.level2.typecheck.IndividualTypeNode))
register_type_strategy(
    concat.level2.typecheck.AttributeTypeNode, attr_type_node)

named_type_node = builds(concat.level2.typecheck.NamedTypeNode,
                         location=infer, name=one_of(just('int'), just('bool'), just('object')))
register_type_strategy(
    concat.level2.typecheck.NamedTypeNode, named_type_node)

typed_program = lists(one_of(builds(concat.level2.parse.CastWordNode), from_type(
    concat.level1.parse.SimpleValueWordNode), from_type(concat.level0.parse.StatementNode))).filter(lambda x: len(x) == 0 or not isinstance(x[0], concat.level2.parse.CastWordNode))

# print(from_type(concat.level0.parse.WordNode))
# print(from_type(Iterable[concat.level0.parse.WordNode]))


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

    @unittest.skip('fails on del statements')
    @given(typed_program)
    def test_whole_program(self, program: concat.astutils.WordsOrStatements) -> None:
        concat.level1.typecheck.infer(concat.level1.typecheck.Environment(
        ), program, (concat.level2.typecheck.infer,), True)

    @given(from_type(Tuple[concat.level1.typecheck.IndividualType, concat.level1.typecheck.IndividualType]).filter(lambda ts: ts[0].is_subtype_of(ts[1])))
    def test_unify_ind(self, types: Tuple[concat.level1.typecheck.IndividualType, concat.level1.typecheck.IndividualType]) -> None:
        type_1, type_2 = types
        concat.level1.typecheck.unify_ind(type_1, type_2)

    def test_function_with_stack_effect(self) -> None:
        funcdef = 'def f(a b -- c): ()\n'
        tree = parse(funcdef)
        self.assertRaises(concat.level1.typecheck.TypeError,
                          concat.level1.typecheck.infer, concat.level1.typecheck.Environment(), tree.children, (concat.level2.typecheck.infer,), True)


class TestStackEffectParser(unittest.TestCase):
    _a_bar = concat.level1.typecheck.SequenceVariable()
    _d_bar = concat.level1.typecheck.SequenceVariable()
    _b = concat.level1.typecheck.IndividualVariable()
    _c = concat.level1.typecheck.IndividualVariable()
    examples: Dict[str, concat.level1.typecheck.StackEffect] = {
        'a b -- b a': concat.level1.typecheck.StackEffect(
            [_a_bar, _b, _c], [_a_bar, _c, _b]),
        'a -- a a': concat.level1.typecheck.StackEffect(
            [_a_bar, _b],
            [_a_bar, _b, _b]),
        'a --': concat.level1.typecheck.StackEffect(
            [_a_bar, _b], [_a_bar]),
        'a:object b:object -- b a': concat.level1.typecheck.StackEffect(
            [
                _a_bar,
                concat.level1.typecheck.PrimitiveTypes.object,
                concat.level1.typecheck.PrimitiveTypes.object
            ], [_a_bar, *[concat.level1.typecheck.PrimitiveTypes.object] * 2]),
        'a:`t -- a a': concat.level1.typecheck.StackEffect(
            [_a_bar, _b], [_a_bar, _b, _b]),
        '*i -- *i a': concat.level1.typecheck.StackEffect(
            [_a_bar], [_a_bar, _b]
        ),
        '*i fun:(*i -- *o) -- *o': concat.level1.typecheck.StackEffect(
            [_a_bar, concat.level1.typecheck.StackEffect([_a_bar], [_d_bar])],
            [_d_bar]
        )
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
                self.assertEqual(concat.level2.typecheck.ast_to_type(
                    effect, subs, env)[0], self.examples[example])
