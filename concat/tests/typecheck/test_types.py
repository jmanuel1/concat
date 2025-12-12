import unittest

from concat.typecheck import (
    TypeChecker,
)
from concat.typecheck.context import change_context
from concat.typecheck.errors import TypeError as ConcatTypeError
from concat.typecheck.substitutions import Substitutions
from concat.typecheck.types import (
    BoundVariable,
    Fix,
    GenericType,
    IndividualKind,
    ItemKind,
    ItemVariable,
    ObjectType,
    SequenceVariable,
    StackEffect,
    TupleKind,
    TypeSequence,
    TypeTuple,
)

context = TypeChecker()
context.load_builtins_and_preamble()


def setUpModule() -> None:
    unittest.enterModuleContext(change_context(context))


class TestIndividualVariableConstrain(unittest.TestCase):
    def test_individual_variable_subtype(self) -> None:
        v = ItemVariable(IndividualKind)
        ty = context.int_type
        v.constrain_and_bind_variables(context, ty, set(), [])
        self.assertTrue(ty.equals(context, v))

    def test_individual_variable_supertype(self) -> None:
        v = ItemVariable(IndividualKind)
        ty = context.int_type
        ty.constrain_and_bind_variables(context, v, set(), [])
        self.assertTrue(ty.equals(context, v))

    def test_attribute_subtype(self) -> None:
        v = ItemVariable(IndividualKind)
        attr_ty = ObjectType({'__add__': v})
        ty = context.int_type
        with self.assertRaises(ConcatTypeError):
            attr_ty.constrain_and_bind_variables(context, ty, set(), [])

    def test_attribute_supertype(self) -> None:
        v = ItemVariable(IndividualKind)
        attr_ty = ObjectType({'__add__': v})
        ty = context.int_type
        ty.constrain_and_bind_variables(context, attr_ty, set(), [])
        self.assertTrue(
            ty.get_type_of_attribute(context, '__add__').equals(context, v)
        )

    def test_py_function_return_subtype(self) -> None:
        v = ItemVariable(IndividualKind)
        py_fun_ty = context.py_function_type.apply(
            context, [TypeSequence(context, [context.int_type]), v]
        )
        ty = context.int_type.get_type_of_attribute(context, '__add__')
        py_fun_ty.constrain_and_bind_variables(context, ty, set(), [])
        self.assertTrue(context.int_type.equals(context, v))

    def test_py_function_return_supertype(self) -> None:
        v = ItemVariable(IndividualKind)
        py_fun_ty = context.py_function_type[
            TypeSequence(context, [context.int_type]), v
        ]
        ty = context.int_type.get_type_of_attribute(context, '__add__')
        ty.constrain_and_bind_variables(context, py_fun_ty, set(), [])
        self.assertTrue(context.int_type.equals(context, v))

    def test_type_sequence_subtype(self) -> None:
        v = ItemVariable(IndividualKind)
        seq_ty = TypeSequence(context, [v])
        ty = TypeSequence(context, [context.int_type])
        seq_ty.constrain_and_bind_variables(context, ty, set(), [])
        self.assertTrue(context.int_type.equals(context, v))

    def test_type_sequence_supertype(self) -> None:
        v = ItemVariable(IndividualKind)
        seq_ty = TypeSequence(context, [v])
        ty = TypeSequence(context, [context.int_type])
        ty.constrain_and_bind_variables(context, seq_ty, set(), [])
        self.assertTrue(context.int_type.equals(context, v))

    def test_int_addable(self) -> None:
        v = ItemVariable(IndividualKind)
        context.int_type.constrain_and_bind_variables(
            context, context.addable_type[v, v], set(), []
        )
        self.assertTrue(context.int_type.equals(context, v))

    def test_int__add__addable__add__(self) -> None:
        v = ItemVariable(IndividualKind)
        int_add = context.int_type.get_type_of_attribute(context, '__add__')
        addable_add = context.addable_type[v, v].get_type_of_attribute(
            context, '__add__'
        )
        int_add.constrain_and_bind_variables(context, addable_add, set(), [])
        self.assertTrue(context.int_type.equals(context, v))


class TestSequenceVariableConstrain(unittest.TestCase):
    def test_stack_effect_input_subtype(self) -> None:
        v = SequenceVariable()
        effect_ty = StackEffect(
            TypeSequence(context, [v]), TypeSequence(context, [])
        )
        ty = StackEffect(TypeSequence(context, []), TypeSequence(context, []))
        effect_ty.constrain_and_bind_variables(context, ty, set(), [])
        self.assertTrue(TypeSequence(context, []).equals(context, v))

    def test_stack_effect_input_supertype(self) -> None:
        v = SequenceVariable()
        effect_ty = StackEffect(
            TypeSequence(context, [v]), TypeSequence(context, [])
        )
        ty = StackEffect(TypeSequence(context, []), TypeSequence(context, []))
        ty.constrain_and_bind_variables(context, effect_ty, set(), [])
        self.assertTrue(TypeSequence(context, []).equals(context, v))


class TestFix(unittest.TestCase):
    with change_context(context):
        fix_var = BoundVariable(IndividualKind)
        linked_list = Fix(
            fix_var,
            context.optional_type[
                context.tuple_type[context.object_type, fix_var],
            ],
        )

    def test_unroll_supertype(self) -> None:
        with context.substitutions.push() as subs:
            self.linked_list.constrain_and_bind_variables(
                context, self.linked_list.unroll(context), set(), []
            )
        self.assertEqual(
            Substitutions(),
            subs,
        )

    def test_unroll_subtype(self) -> None:
        with context.substitutions.push() as subs:
            self.linked_list.unroll(context).constrain_and_bind_variables(
                context, self.linked_list, set(), []
            )
        self.assertEqual(
            Substitutions(),
            subs,
        )

    def test_unroll_equal(self) -> None:
        self.assertTrue(
            self.linked_list.unroll(context).equals(context, self.linked_list)
        )
        self.assertTrue(
            self.linked_list.equals(context, self.linked_list.unroll(context))
        )


class TestTypeSequence(unittest.TestCase):
    def test_constrain_empty(self) -> None:
        with context.substitutions.push() as subs:
            TypeSequence(context, []).constrain_and_bind_variables(
                context, TypeSequence(context, []), set(), []
            )
        self.assertEqual(
            Substitutions(),
            subs,
        )

    def test_empty_equal(self) -> None:
        self.assertTrue(
            TypeSequence(context, []).equals(
                context, TypeSequence(context, [])
            )
        )


class TestGeneric(unittest.TestCase):
    def test_generalize(self) -> None:
        a, b = BoundVariable(ItemKind), BoundVariable(ItemKind)
        subtype = GenericType([a], context.int_type)
        supertype = GenericType([a, b], context.int_type)
        subtype.constrain_and_bind_variables(context, supertype, set(), [])

    def test_parameter_kinds(self) -> None:
        ind = BoundVariable(IndividualKind)
        item = BoundVariable(ItemKind)
        subtype = GenericType([ind], ind)
        supertype = GenericType([item], item)
        with self.assertRaises(ConcatTypeError):
            subtype.constrain_and_bind_variables(context, supertype, set(), [])


class TestTypeTuples(unittest.TestCase):
    def test_empty_tuple(self) -> None:
        self.assertTrue(TypeTuple([]).equals(context, TypeTuple([])))

    def test_equal(self) -> None:
        self.assertTrue(
            TypeTuple([context.int_type]).equals(
                context, TypeTuple([context.int_type])
            )
        )

    def test_unequal_lengths(self) -> None:
        with self.assertRaises(Exception) as cm:
            TypeTuple([context.int_type]).constrain_and_bind_variables(
                context, TypeTuple([]), set(), []
            )
        self.assertNotIsInstance(cm.exception, ConcatTypeError)

    def test_not_subtype(self) -> None:
        with self.assertRaises(ConcatTypeError):
            TypeTuple([context.int_type]).constrain_and_bind_variables(
                context, TypeTuple([context.no_return_type]), set(), []
            )

    @staticmethod
    def test_subtype() -> None:
        TypeTuple([context.int_type]).constrain_and_bind_variables(
            context, TypeTuple([context.object_type]), set(), []
        )

    def test_projection(self) -> None:
        self.assertTrue(
            TypeTuple([context.int_type])
            .project(context, 0)
            .equals(context, context.int_type)
        )

    def test_unsupported_projection(self) -> None:
        with self.assertRaises(Exception) as cm:
            TypeTuple([context.int_type]).project(context, 1)
        self.assertNotIsInstance(cm.exception, ConcatTypeError)

    def test_kind(self) -> None:
        self.assertEqual(
            TypeTuple([context.int_type]).kind, TupleKind([IndividualKind])
        )


class TestOverloadedFunctions(unittest.TestCase):
    def test_py_overloaded_can_be_instantiated(self) -> None:
        t = context.py_overloaded_type.instantiate(context)
        self.assertFalse(
            any(
                isinstance(v, BoundVariable)
                for v in t.free_type_variables(context)
            )
        )

    def test_py_overloaded_no_overloads(self) -> None:
        t = context.py_overloaded_type[()]
        self.assertFalse(t.free_type_variables(context))
        context.object_type.constrain_and_bind_variables(context, t, set(), [])
        self.assertTrue(context.object_type.equals(context, t))
