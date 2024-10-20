from concat.typecheck import (
    Environment,
    Substitutions,
    TypeError as ConcatTypeError,
    load_builtins_and_preamble,
)
from concat.typecheck.types import (
    BoundVariable,
    Fix,
    ForwardTypeReference,
    GenericType,
    IndividualKind,
    ItemKind,
    ItemVariable,
    ObjectType,
    SequenceVariable,
    StackEffect,
    TypeSequence,
    addable_type,
    get_int_type,
    get_object_type,
    optional_type,
    py_function_type,
    get_tuple_type,
)
import unittest


load_builtins_and_preamble()


class TestIndividualVariableConstrain(unittest.TestCase):
    def test_individual_variable_subtype(self) -> None:
        v = ItemVariable(IndividualKind)
        ty = get_int_type()
        sub = v.constrain_and_bind_variables(ty, set(), [])
        self.assertEqual(ty, sub(v))

    def test_individual_variable_supertype(self) -> None:
        v = ItemVariable(IndividualKind)
        ty = get_int_type()
        sub = ty.constrain_and_bind_variables(v, set(), [])
        self.assertEqual(ty, sub(v))

    def test_attribute_subtype(self) -> None:
        v = ItemVariable(IndividualKind)
        attr_ty = ObjectType({'__add__': v})
        ty = get_int_type()
        with self.assertRaises(ConcatTypeError):
            attr_ty.constrain_and_bind_variables(ty, set(), [])

    def test_attribute_supertype(self) -> None:
        v = ItemVariable(IndividualKind)
        attr_ty = ObjectType({'__add__': v})
        ty = get_int_type()
        sub = ty.constrain_and_bind_variables(attr_ty, set(), [])
        self.assertEqual(ty.get_type_of_attribute('__add__'), sub(v))

    def test_py_function_return_subtype(self) -> None:
        v = ItemVariable(IndividualKind)
        py_fun_ty = py_function_type[TypeSequence([get_int_type()]), v]
        ty = get_int_type().get_type_of_attribute('__add__')
        sub = py_fun_ty.constrain_and_bind_variables(ty, set(), [])
        self.assertEqual(get_int_type(), sub(v))

    def test_py_function_return_supertype(self) -> None:
        v = ItemVariable(IndividualKind)
        py_fun_ty = py_function_type[TypeSequence([get_int_type()]), v]
        ty = get_int_type().get_type_of_attribute('__add__')
        sub = ty.constrain_and_bind_variables(py_fun_ty, set(), [])
        self.assertEqual(get_int_type(), sub(v))

    def test_type_sequence_subtype(self) -> None:
        v = ItemVariable(IndividualKind)
        seq_ty = TypeSequence([v])
        ty = TypeSequence([get_int_type()])
        sub = seq_ty.constrain_and_bind_variables(ty, set(), [])
        self.assertEqual(get_int_type(), sub(v))

    def test_type_sequence_supertype(self) -> None:
        v = ItemVariable(IndividualKind)
        seq_ty = TypeSequence([v])
        ty = TypeSequence([get_int_type()])
        sub = ty.constrain_and_bind_variables(seq_ty, set(), [])
        self.assertEqual(get_int_type(), sub(v))

    def test_int_addable(self) -> None:
        v = ItemVariable(IndividualKind)
        sub = get_int_type().constrain_and_bind_variables(
            addable_type[v, v], set(), []
        )
        self.assertEqual(get_int_type(), sub(v))

    def test_int__add__addable__add__(self) -> None:
        v = ItemVariable(IndividualKind)
        int_add = get_int_type().get_type_of_attribute('__add__')
        addable_add = addable_type[v, v].get_type_of_attribute('__add__')
        sub = int_add.constrain_and_bind_variables(addable_add, set(), [])
        print(v)
        print(int_add)
        print(addable_add)
        print(sub)
        self.assertEqual(get_int_type(), sub(v))


class TestSequenceVariableConstrain(unittest.TestCase):
    def test_stack_effect_input_subtype(self) -> None:
        v = SequenceVariable()
        effect_ty = StackEffect(TypeSequence([v]), TypeSequence([]))
        ty = StackEffect(TypeSequence([]), TypeSequence([]))
        sub = effect_ty.constrain_and_bind_variables(ty, set(), [])
        self.assertEqual(TypeSequence([]), sub(v))

    def test_stack_effect_input_supertype(self) -> None:
        v = SequenceVariable()
        effect_ty = StackEffect(TypeSequence([v]), TypeSequence([]))
        ty = StackEffect(TypeSequence([]), TypeSequence([]))
        sub = ty.constrain_and_bind_variables(effect_ty, set(), [])
        self.assertEqual(TypeSequence([]), sub(v))


class TestFix(unittest.TestCase):
    fix_var = BoundVariable(IndividualKind)
    linked_list = Fix(
        fix_var,
        optional_type[get_tuple_type()[get_object_type(), fix_var],],
    )

    def test_unroll_supertype(self) -> None:
        self.assertEqual(
            Substitutions(),
            self.linked_list.constrain_and_bind_variables(
                self.linked_list.unroll(), set(), []
            ),
        )

    def test_unroll_subtype(self) -> None:
        self.assertEqual(
            Substitutions(),
            self.linked_list.unroll().constrain_and_bind_variables(
                self.linked_list, set(), []
            ),
        )

    def test_unroll_equal(self) -> None:
        self.assertEqual(self.linked_list.unroll(), self.linked_list)
        self.assertEqual(self.linked_list, self.linked_list.unroll())


class TestForwardReferences(unittest.TestCase):
    env = Environment({'ty': get_object_type()})
    ty = ForwardTypeReference(
        IndividualKind, 'ty', lambda: TestForwardReferences.env
    )

    def test_resolve_supertype(self) -> None:
        self.assertEqual(
            Substitutions(),
            self.ty.constrain_and_bind_variables(
                self.ty.resolve_forward_references(), set(), []
            ),
        )

    def test_resolve_subtype(self) -> None:
        self.assertEqual(
            Substitutions(),
            self.ty.resolve_forward_references().constrain_and_bind_variables(
                self.ty, set(), []
            ),
        )

    def test_resolve_equal(self) -> None:
        self.assertEqual(self.ty.resolve_forward_references(), self.ty)
        self.assertEqual(self.ty, self.ty.resolve_forward_references())


class TestTypeSequence(unittest.TestCase):
    def test_constrain_empty(self) -> None:
        self.assertEqual(
            Substitutions(),
            TypeSequence([]).constrain_and_bind_variables(
                TypeSequence([]), set(), []
            ),
        )

    def test_empty_equal(self) -> None:
        self.assertEqual(TypeSequence([]), TypeSequence([]))


class TestGeneric(unittest.TestCase):
    def test_generalize(self) -> None:
        a, b = BoundVariable(ItemKind), BoundVariable(ItemKind)
        subtype = GenericType([a], get_int_type())
        supertype = GenericType([a, b], get_int_type())
        subtype.constrain_and_bind_variables(supertype, set(), [])

    def test_parameter_kinds(self) -> None:
        ind = BoundVariable(IndividualKind)
        item = BoundVariable(ItemKind)
        subtype = GenericType([ind], ind)
        supertype = GenericType([item], item)
        with self.assertRaises(ConcatTypeError):
            subtype.constrain_and_bind_variables(supertype, set(), [])
