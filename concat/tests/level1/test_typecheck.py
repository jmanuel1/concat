import concat.lex
import concat.level0.parse
import concat.level1.parse
import concat.level1.typecheck
from concat.level1.typecheck import Environment
from concat.level1.typecheck.types import (
    ClassType,
    IndividualType,
    IndividualVariable,
    ObjectType,
    SequenceVariable,
    StackEffect,
    StackItemType,
    Type as ConcatType,
    TypeSequence,
    bool_type,
    ellipsis_type,
    float_type,
    int_type,
    list_type,
    none_type,
    no_return_type,
    not_implemented_type,
    object_type,
    py_function_type,
)
from concat.level1.preamble_types import types
import concat.tests.strategies
import unittest
from hypothesis import HealthCheck, assume, example, given, note, settings
from hypothesis.strategies import (
    SearchStrategy,
    booleans,
    composite,
    from_type,
    dictionaries,
    integers,
    lists,
    sampled_from,
    text,
)
from typing import Iterable, Sequence, Type, cast


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


in_var = SequenceVariable()
f = StackEffect(
    [in_var, object_type, object_type], [in_var, object_type, object_type]
)


class TestStackEffectAlgebra(unittest.TestCase):
    def test_composition(self) -> None:
        in_var = SequenceVariable()
        in_var2 = SequenceVariable()
        g = StackEffect([in_var, object_type], [in_var, *[object_type] * 2])
        f_then_g = f.compose(g)
        self.assertEqual(
            f_then_g,
            StackEffect(
                [in_var2, *[object_type] * 2], [in_var2, *[object_type] * 3]
            ),
        )

    def test_composition_with_overflow(self) -> None:
        in_var = SequenceVariable()
        in_var2 = SequenceVariable()
        g = StackEffect([in_var, *[object_type] * 4], [in_var, object_type])
        f_then_g = f.compose(g)
        self.assertEqual(
            f_then_g,
            StackEffect([in_var2, *[object_type] * 4], [in_var2, object_type]),
        )


class TestStackEffectProperties(unittest.TestCase):
    def test_completeness_test(self) -> None:
        self.assertFalse(f.can_be_complete_program())


class TestTypeChecker(unittest.TestCase):
    def test_with_word(self) -> None:
        wth = '$() ctxmgr with\n'
        tree = parse(wth)
        a_bar = SequenceVariable()
        self.assertRaises(
            concat.level1.typecheck.TypeError,
            concat.level1.typecheck.infer,
            concat.level1.typecheck.Environment(
                {
                    'ctxmgr': concat.level1.typecheck.ForAll(
                        [a_bar], StackEffect([a_bar], [a_bar, object_type])
                    )
                }
            ),
            tree.children,
        )

    def test_try_word(self) -> None:
        try_prog = '$() $() try\n'
        tree = parse(try_prog)
        concat.level1.typecheck.infer(
            concat.level1.typecheck.Environment(), tree.children
        )

    @given(from_type(concat.level0.parse.AttributeWordNode))
    def test_attribute_word(self, attr_word) -> None:
        _, type = concat.level1.typecheck.infer(
            concat.level1.typecheck.Environment(),
            [attr_word],
            initial_stack=TypeSequence(
                [
                    ObjectType(
                        IndividualVariable(),
                        {attr_word.value: StackEffect([], [int_type]),},
                    ),
                ]
            ),
        )
        self.assertEqual(list(type.output), [int_type])

    @given(integers(min_value=0), integers(min_value=0))
    def test_add_operator_inference(self, a: int, b: int) -> None:
        try_prog = '{!r} {!r} +\n'.format(a, b)
        tree = parse(try_prog)
        _, type = concat.level1.typecheck.infer(
            concat.level1.typecheck.Environment(),
            tree.children,
            is_top_level=True,
        )
        note(type)
        self.assertEqual(type, StackEffect([], [int_type]))

    def test_if_then_inference(self) -> None:
        try_prog = 'True $() if_then\n'
        tree = parse(try_prog)
        _, type = concat.level1.typecheck.infer(
            concat.level1.typecheck.Environment(types),
            tree.children,
            is_top_level=True,
        )
        self.assertEqual(type, StackEffect([], []))

    def test_call_inference(self) -> None:
        try_prog = '$(42) call\n'
        tree = parse(try_prog)
        _, type = concat.level1.typecheck.infer(
            concat.level1.typecheck.Environment(types),
            tree.children,
            is_top_level=True,
        )
        self.assertEqual(type, StackEffect([], [int_type]))

    @given(from_type(concat.level1.parse.SimpleValueWordNode))
    def test_simple_value_word(self, simple_value_word) -> None:
        _, effect = concat.level1.typecheck.infer(
            concat.level1.typecheck.Environment(),
            [simple_value_word],
            initial_stack=TypeSequence([]),
        )
        expected_types = {
            concat.level1.parse.NoneWordNode: none_type,
            concat.level1.parse.NotImplWordNode: not_implemented_type,
            concat.level1.parse.EllipsisWordNode: ellipsis_type,
        }
        expected_type = expected_types[type(simple_value_word)]
        self.assertEqual(list(effect.output), [expected_type])

    def test_slice_inference(self) -> None:
        slice_prog = '[1, 2, 3, 4, 5, 6, 7, 8] $[1:None:2]\n'
        tree = parse(slice_prog)
        _, type = concat.level1.typecheck.infer(
            Environment(types), tree.children, is_top_level=True,
        )
        self.assertEqual(type, StackEffect([], [list_type[int_type,]]))


class TestDiagnosticInfo(unittest.TestCase):
    def test_attribute_error_location(self) -> None:
        bad_code = '5 .attr'
        tree = parse(bad_code)
        try:
            concat.level1.typecheck.infer(
                concat.level1.typecheck.Environment(), tree.children
            )
        except concat.level1.typecheck.TypeError as e:
            self.assertEqual(e.location, tree.children[1].location)
        else:
            self.fail('no type error')


class TestTypeEquality(unittest.TestCase):
    @given(from_type(ConcatType))
    @example(type=int_type.self_type)
    @example(type=int_type.get_type_of_attribute('__add__'))
    @example(type=int_type)
    @example(
        type=ObjectType(
            IndividualVariable(),
            {
                '': (
                    IndividualVariable()
                    & StackEffect(TypeSequence([]), TypeSequence([]))
                )
            },
            (),
            (),
            False,
            [],
            None,
        )
    )
    @example(
        type=IndividualVariable()
        & StackEffect(TypeSequence([]), TypeSequence([]))
    )
    def test_reflexive_equality(self, type):
        self.assertEqual(type, type)


class TestSubtyping(unittest.TestCase):
    def test_int_not_subtype_of_float(self):
        """Differ from Reticulated Python: !(int <= float)."""
        self.assertFalse(int_type <= float_type)

    @given(from_type(IndividualType), from_type(IndividualType))
    @settings(suppress_health_check=(HealthCheck.filter_too_much,))
    def test_stack_effect_subtyping(self, type1, type2):
        fun1 = StackEffect([type1], [type2])
        fun2 = StackEffect([no_return_type], [object_type])
        self.assertLessEqual(fun1, fun2)

    @given(from_type(IndividualType))
    def test_no_return_is_bottom_type(self, type):
        self.assertLessEqual(no_return_type, type)

    @given(from_type(IndividualType))
    def test_object_is_top_type(self, type):
        self.assertLessEqual(type, object_type)

    __attributes_generator = dictionaries(
        text(max_size=25), from_type(IndividualType), max_size=5  # type: ignore
    )

    @given(__attributes_generator, __attributes_generator)
    @settings(suppress_health_check=(HealthCheck.filter_too_much,))
    def test_object_structural_subtyping(self, attributes, other_attributes):
        x1, x2 = IndividualVariable(), IndividualVariable()
        object1 = ObjectType(x1, {**other_attributes, **attributes})
        object2 = ObjectType(x2, attributes)
        self.assertLessEqual(object1, object2)

    @given(__attributes_generator, __attributes_generator)
    @settings(suppress_health_check=(HealthCheck.filter_too_much,))
    def test_class_structural_subtyping(self, attributes, other_attributes):
        x1, x2 = IndividualVariable(), IndividualVariable()
        object1 = ClassType(x1, {**other_attributes, **attributes})
        object2 = ClassType(x2, attributes)
        self.assertLessEqual(object1, object2)

    @given(from_type(StackEffect))
    @settings(suppress_health_check=(HealthCheck.filter_too_much,))
    def test_object_subtype_of_stack_effect(self, effect):
        x = IndividualVariable()
        object = ObjectType(x, {'__call__': effect})
        self.assertLessEqual(object, effect)

    @given(from_type(IndividualType), from_type(IndividualType))
    @settings(suppress_health_check=(HealthCheck.filter_too_much,))
    def test_object_subtype_of_py_function(self, type1, type2):
        x = IndividualVariable()
        py_function = py_function_type[TypeSequence([type1]), type2]
        object = ObjectType(x, {'__call__': py_function})
        self.assertLessEqual(object, py_function)

    @given(from_type(StackEffect))
    def test_class_subtype_of_stack_effect(self, effect):
        x = IndividualVariable()
        # NOTE: self-last convention is modelled after Factor.
        unbound_effect = StackEffect([*effect.input, x], effect.output)
        cls = ClassType(x, {'__init__': unbound_effect})
        self.assertLessEqual(cls, effect)

    @given(from_type(IndividualType), from_type(IndividualType))
    @settings(suppress_health_check=(HealthCheck.filter_too_much,))
    def test_class_subtype_of_py_function(self, type1, type2):
        x = IndividualVariable()
        py_function = py_function_type[TypeSequence([type1]), type2]
        unbound_py_function = py_function_type[TypeSequence([x, type1]), type2]
        cls = ClassType(x, {'__init__': unbound_py_function})
        self.assertLessEqual(cls, py_function)
