import concat.lex
import concat.level0.parse
import concat.level1.parse
import concat.level1.typecheck
import unittest
from typing import cast


def parse(string: str) -> concat.level0.parse.TopLevelNode:
    tokens = concat.lex.tokenize(string)
    parsers = build_parsers()
    tree = cast(concat.level0.parse.TopLevelNode, parsers.parse(tokens))
    return tree


def build_parsers() -> concat.level0.parse.ParserDict:
    parsers = concat.level0.parse.ParserDict()
    parsers.extend_with(concat.level0.parse.level_0_extension)
    parsers.extend_with(concat.level1.parse.level_1_extension)
    return parsers


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

    def test_with_word(self) -> None:
        wth = '$() ctxmgr with\n'
        tree = parse(wth)
        a_bar = concat.level1.typecheck.SequenceVariable()
        self.assertRaises(
            concat.level1.typecheck.TypeError,
            concat.level1.typecheck.infer,
            concat.level1.typecheck.Environment({'ctxmgr': concat.level1.typecheck.ForAll(
                [a_bar],
                concat.level1.typecheck.StackEffect([a_bar], [
                    a_bar, concat.level1.typecheck.PrimitiveTypes.object]))}),
            tree.children)

    @unittest.skip('needs subtyping to succeed')
    def test_try_word(self) -> None:
        try_prog = '$() $() try\n'
        tree = parse(try_prog)
        concat.level1.typecheck.infer(
            concat.level1.typecheck.Environment(), tree.children)


class TestDiagnosticInfo(unittest.TestCase):

    def test_attribute_error_location(self) -> None:
        bad_code = '5 .attr'
        tree = parse(bad_code)
        try:
            concat.level1.typecheck.infer(
                concat.level1.typecheck.Environment(), tree.children)
        except concat.level1.typecheck.TypeError as e:
            self.assertEqual(e.location, tree.children[1].location)
        else:
            self.fail('no type error')


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
