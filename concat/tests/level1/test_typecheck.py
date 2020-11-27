import concat.lex
import concat.level0.parse
import concat.level1.parse
import concat.level1.typecheck
from concat.level1.typecheck.types import StackEffect, IndividualType, IndividualVariable, ObjectType, ClassType, Type, int_type, float_type, no_return_type, object_type, py_function_type
import unittest
from hypothesis import given
from hypothesis.strategies import from_type, dictionaries, text
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
            concat.level1.typecheck.Environment({
                'ctxmgr': concat.level1.typecheck.ForAll(
                    [a_bar],
                    concat.level1.typecheck.StackEffect([a_bar], [
                        a_bar, concat.level1.typecheck.PrimitiveTypes.object]))
            }),
            tree.children)

    def test_try_word(self) -> None:
        try_prog = '$() $() try\n'
        tree = parse(try_prog)
        concat.level1.typecheck.infer(
            concat.level1.typecheck.Environment(), tree.children)

    @given(from_type(concat.level0.parse.AttributeWordNode))
    def test_attribute_word(self, attr_word) -> None:
        _, type = concat.level1.typecheck.infer(
            concat.level1.typecheck.Environment(), [attr_word]
        )
        type = type.collapse_bounds()
        attr_type = cast(concat.level1.typecheck.TypeWithAttribute, type.input[-1])
        self.assertEqual(attr_type.attribute, attr_word.value)

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

    def test_with_word_inference(self):
        wth = '$(drop 0 ~) {"file": "a_file"} open with'
        tree = parse(wth)
        _, type = concat.level1.typecheck.infer(Environment({
            'drop': concat.level1.typecheck.ForAll(
                [in_var],
                concat.level1.typecheck.StackEffect(
                    [in_var, concat.level1.typecheck.PrimitiveTypes.object],
                    [in_var])),
            'open': concat.level1.typecheck.ForAll(
                [in_var],
                concat.level1.typecheck.StackEffect(
                    [in_var, concat.level1.typecheck.PrimitiveTypes.dict],
                    [in_var, concat.level1.typecheck.PrimitiveTypes.file]))}),
            tree.children)
        self.assertEqual(type, concat.level1.typecheck.StackEffect(
            [in_var], [in_var, concat.level1.typecheck.PrimitiveTypes.int]))


class TestSubtyping(unittest.TestCase):

    __attributes_generator = dictionaries(
        text(max_size=25), from_type(IndividualType), max_size=5)  # type: ignore

    @given(__attributes_generator, __attributes_generator)
    def test_object_structural_subtyping(self, attributes, other_attributes):
        x1, x2 = IndividualVariable(), IndividualVariable()
        object1 = ObjectType(x1, {**other_attributes, **attributes})
        object2 = ObjectType(x2, attributes)
        self.assertLessEqual(object1, object2)

    @given(__attributes_generator, __attributes_generator)
    def test_class_structural_subtyping(self, attributes, other_attributes):
        x1, x2 = IndividualVariable(), IndividualVariable()
        object1 = ClassType(x1, {**other_attributes, **attributes})
        object2 = ClassType(x2, attributes)
        self.assertLessEqual(object1, object2)

    @given(from_type(StackEffect))
    def test_object_subtype_of_stack_effect(self, effect):
        x = IndividualVariable()
        object = ObjectType(x, {'__call__': effect})
        self.assertLessEqual(object, effect)

    @given(from_type(IndividualType), from_type(IndividualType))
    def test_object_subtype_of_py_function(self, type1, type2):
        x = IndividualVariable()
        py_function = py_function_type[type1, type2]
        object = ObjectType(x, {'__call__': py_function})
        self.assertLessEqual(object, py_function)
