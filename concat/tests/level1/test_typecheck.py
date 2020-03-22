import concat.level0.lex
import concat.level0.parse
import concat.level1.lex as lex
import concat.level1.parse
import concat.level1.typecheck
import unittest
from typing import Dict, List, cast
import parsy


def lex_string(string: str) -> List[concat.level0.lex.Token]:
    tokens = []
    lex.lexer.input(string)
    while True:
        token = lex.lexer.token()
        if token is None:
            break
        tokens.append(token)
    return tokens


def parse(string: str) -> concat.level0.parse.TopLevelNode:
    tokens = lex_string(string)
    parsers = concat.level0.parse.ParserDict()
    parsers.extend_with(concat.level0.parse.level_0_extension)
    parsers.extend_with(concat.level1.parse.level_1_extension)
    tree = cast(concat.level0.parse.TopLevelNode, parsers.parse(tokens))
    return tree


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
                    effect = concat.level1.typecheck.parse_stack_effect(tokens)
                except parsy.ParseError as e:
                    self.fail('could not parse {}\n{}'.format(example, e))
                self.assertEqual(effect, self.examples[example])


in_var = concat.level1.typecheck.SequenceVariable()
f = concat.level1.typecheck.StackEffect(
    [
        in_var,
        concat.level1.typecheck.PrimitiveTypes.object,
        concat.level1.typecheck.PrimitiveTypes.object
    ], [
        in_var,
        concat.level1.typecheck.PrimitiveTypes.object,
        concat.level1.typecheck.PrimitiveTypes.object
    ])


class TestStackEffectAlgebra(unittest.TestCase):

    def test_composition(self) -> None:
        in_var = concat.level1.typecheck.SequenceVariable()
        in_var2 = concat.level1.typecheck.SequenceVariable()
        g = concat.level1.typecheck.StackEffect(
            [in_var, concat.level1.typecheck.PrimitiveTypes.object],
            [in_var, *[concat.level1.typecheck.PrimitiveTypes.object] * 2])
        f_then_g = f.compose(g)
        self.assertEqual(f_then_g, concat.level1.typecheck.StackEffect(
            [in_var2, *[concat.level1.typecheck.PrimitiveTypes.object] * 2],
            [in_var2, *[concat.level1.typecheck.PrimitiveTypes.object] * 3]))

    def test_composition_with_overflow(self) -> None:
        in_var = concat.level1.typecheck.SequenceVariable()
        in_var2 = concat.level1.typecheck.SequenceVariable()
        g = concat.level1.typecheck.StackEffect(
            [in_var, *[concat.level1.typecheck.PrimitiveTypes.object] * 4],
            [in_var, concat.level1.typecheck.PrimitiveTypes.object])
        f_then_g = f.compose(g)
        self.assertEqual(f_then_g, concat.level1.typecheck.StackEffect(
            [in_var2, *[concat.level1.typecheck.PrimitiveTypes.object] * 4],
            [in_var2, concat.level1.typecheck.PrimitiveTypes.object]))


class TestStackEffectProperties(unittest.TestCase):

    def test_completeness_test(self) -> None:
        self.assertFalse(f.can_be_complete_program())


class TestTypeChecker(unittest.TestCase):

    def test_function_with_stack_effect(self) -> None:
        funcdef = 'def f(a b -- c): ()\n'
        tree = parse(funcdef)
        self.assertRaises(concat.level1.typecheck.TypeError,
                          concat.level1.typecheck.infer, {}, tree.children)

    def test_with_word(self) -> None:
        wth = '$() ctxmgr with\n'
        tree = parse(wth)
        a_bar = concat.level1.typecheck.SequenceVariable()
        self.assertRaises(
            concat.level1.typecheck.TypeError,
            concat.level1.typecheck.infer,
            {'ctxmgr': concat.level1.typecheck.ForAll(
                [a_bar],
                concat.level1.typecheck.StackEffect([a_bar], [
                  a_bar, concat.level1.typecheck.PrimitiveTypes.object]))},
            tree.children)

    @unittest.skip('needs subtyping to succeed')
    def test_try_word(self) -> None:
        try_prog = '$() $() try\n'
        tree = parse(try_prog)
        concat.level1.typecheck.infer(
            concat.level1.typecheck.Environment(), tree.children)


class TestSequenceVariableTypeInference(unittest.TestCase):

    @unittest.skip('needs subtyping to pass')
    def test_with_word_inference(self):
        wth = '$(drop 0 ~) {"file": "a_file"} open with'
        tree = parse(wth)
        type = concat.level1.typecheck.infer({
            'drop': concat.level1.typecheck.ForAll(
                [in_var],
                concat.level1.typecheck.StackEffect(
                    [in_var, concat.level1.typecheck.PrimitiveTypes.object],
                    [in_var])),
            'open': concat.level1.typecheck.ForAll(
                [in_var],
                concat.level1.typecheck.StackEffect(
                    [in_var, concat.level1.typecheck.PrimitiveTypes.dict],
                    [in_var, concat.level1.typecheck.PrimitiveTypes.file]))},
            tree.children)
        self.assertEquals(type, concat.level1.typecheck.StackEffect(
            [in_var], [in_var, concat.level1.typecheck.PrimitiveTypes.int]))
