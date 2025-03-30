from concat.typecheck import (
    TypeChecker,
)
from concat.typecheck.substitutions import Substitutions
from concat.typecheck.errors import TypeError as ConcatTypeError
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
    addable_type,
    no_return_type,
    optional_type,
    py_function_type,
    py_overloaded_type,
)
import unittest

context = TypeChecker()
context.load_builtins_and_preamble()


class TestIndividualVariableConstrain(unittest.TestCase):
    def test_individual_variable_subtype(self) -> None:
        v = ItemVariable(IndividualKind)
        ty = context.int_type
        sub = v.constrain_and_bind_variables(context, ty, set(), [])
        self.assertTrue(ty.equals(context, sub(v)))

    def test_individual_variable_supertype(self) -> None:
        v = ItemVariable(IndividualKind)
        ty = context.int_type
        sub = ty.constrain_and_bind_variables(context, v, set(), [])
        self.assertTrue(ty.equals(context, sub(v)))

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
        sub = ty.constrain_and_bind_variables(context, attr_ty, set(), [])
        self.assertTrue(
            ty.get_type_of_attribute('__add__').equals(context, sub(v))
        )

    def test_py_function_return_subtype(self) -> None:
        v = ItemVariable(IndividualKind)
        py_fun_ty = py_function_type[TypeSequence([context.int_type]), v]
        ty = context.int_type.get_type_of_attribute('__add__')
        sub = py_fun_ty.constrain_and_bind_variables(context, ty, set(), [])
        self.assertTrue(context.int_type.equals(context, sub(v)))

    def test_py_function_return_supertype(self) -> None:
        v = ItemVariable(IndividualKind)
        py_fun_ty = py_function_type[TypeSequence([context.int_type]), v]
        ty = context.int_type.get_type_of_attribute('__add__')
        sub = ty.constrain_and_bind_variables(context, py_fun_ty, set(), [])
        self.assertTrue(context.int_type.equals(context, sub(v)))

    def test_type_sequence_subtype(self) -> None:
        v = ItemVariable(IndividualKind)
        seq_ty = TypeSequence([v])
        ty = TypeSequence([context.int_type])
        sub = seq_ty.constrain_and_bind_variables(context, ty, set(), [])
        self.assertTrue(context.int_type.equals(context, sub(v)))

    def test_type_sequence_supertype(self) -> None:
        v = ItemVariable(IndividualKind)
        seq_ty = TypeSequence([v])
        ty = TypeSequence([context.int_type])
        sub = ty.constrain_and_bind_variables(context, seq_ty, set(), [])
        self.assertTrue(context.int_type.equals(context, sub(v)))

    def test_int_addable(self) -> None:
        v = ItemVariable(IndividualKind)
        sub = context.int_type.constrain_and_bind_variables(
            context, addable_type[v, v], set(), []
        )
        self.assertTrue(context.int_type.equals(context, sub(v)))

    def test_int__add__addable__add__(self) -> None:
        v = ItemVariable(IndividualKind)
        int_add = context.int_type.get_type_of_attribute('__add__')
        addable_add = addable_type[v, v].get_type_of_attribute('__add__')
        sub = int_add.constrain_and_bind_variables(
            context, addable_add, set(), []
        )
        print(v)
        print(int_add)
        print(addable_add)
        print(sub)
        self.assertTrue(context.int_type.equals(context, sub(v)))


class TestSequenceVariableConstrain(unittest.TestCase):
    def test_stack_effect_input_subtype(self) -> None:
        v = SequenceVariable()
        effect_ty = StackEffect(TypeSequence([v]), TypeSequence([]))
        ty = StackEffect(TypeSequence([]), TypeSequence([]))
        sub = effect_ty.constrain_and_bind_variables(context, ty, set(), [])
        self.assertTrue(TypeSequence([]).equals(context, sub(v)))

    def test_stack_effect_input_supertype(self) -> None:
        v = SequenceVariable()
        effect_ty = StackEffect(TypeSequence([v]), TypeSequence([]))
        ty = StackEffect(TypeSequence([]), TypeSequence([]))
        sub = ty.constrain_and_bind_variables(context, effect_ty, set(), [])
        self.assertTrue(TypeSequence([]).equals(context, sub(v)))


class TestFix(unittest.TestCase):
    fix_var = BoundVariable(IndividualKind)
    linked_list = Fix(
        fix_var,
        optional_type[context.tuple_type[context.object_type, fix_var],],
    )

    def test_unroll_supertype(self) -> None:
        self.assertEqual(
            Substitutions(),
            self.linked_list.constrain_and_bind_variables(
                context, self.linked_list.unroll(), set(), []
            ),
        )

    def test_unroll_subtype(self) -> None:
        self.assertEqual(
            Substitutions(),
            self.linked_list.unroll().constrain_and_bind_variables(
                context, self.linked_list, set(), []
            ),
        )

    def test_unroll_equal(self) -> None:
        self.assertTrue(
            self.linked_list.unroll().equals(context, self.linked_list)
        )
        self.assertTrue(
            self.linked_list.equals(context, self.linked_list.unroll())
        )


class TestTypeSequence(unittest.TestCase):
    def test_constrain_empty(self) -> None:
        self.assertEqual(
            Substitutions(),
            TypeSequence([]).constrain_and_bind_variables(
                context, TypeSequence([]), set(), []
            ),
        )

    def test_empty_equal(self) -> None:
        self.assertTrue(TypeSequence([]).equals(context, TypeSequence([])))


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
                context, TypeTuple([no_return_type]), set(), []
            )

    @staticmethod
    def test_subtype() -> None:
        TypeTuple([context.int_type]).constrain_and_bind_variables(
            context, TypeTuple([context.object_type]), set(), []
        )

    def test_projection(self) -> None:
        self.assertTrue(
            TypeTuple([context.int_type])
            .project(0)
            .equals(context, context.int_type)
        )

    def test_unsupported_projection(self) -> None:
        with self.assertRaises(Exception) as cm:
            TypeTuple([context.int_type]).project(1)
        self.assertNotIsInstance(cm.exception, ConcatTypeError)

    def test_kind(self) -> None:
        self.assertEqual(
            TypeTuple([context.int_type]).kind, TupleKind([IndividualKind])
        )


class TestOverloadedFunctions(unittest.TestCase):
    def test_py_overloaded_can_be_instantiated(self) -> None:
        t = py_overloaded_type.instantiate()
        self.assertFalse(
            any(isinstance(v, BoundVariable) for v in t.free_type_variables())
        )

    def test_py_overloaded_no_overloads(self) -> None:
        t = py_overloaded_type[()]
        print(t)
        print(t.free_type_variables())
        self.assertFalse(t.free_type_variables())
        context.object_type.constrain_and_bind_variables(context, t, set(), [])
        self.assertTrue(context.object_type.equals(context, t))
