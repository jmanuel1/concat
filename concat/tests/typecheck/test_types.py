from concat.typecheck import (
    TypeError as ConcatTypeError,
    load_builtins_and_preamble,
)
from concat.typecheck.types import (
    IndividualVariable,
    ObjectType,
    SequenceVariable,
    StackEffect,
    TypeSequence,
    addable_type,
    int_type,
    py_function_type,
)
import unittest


load_builtins_and_preamble()


class TestIndividualVariableConstrain(unittest.TestCase):
    def test_individual_variable_subtype(self) -> None:
        v = IndividualVariable()
        ty = int_type
        sub = v.constrain_and_bind_variables(ty, set(), [])
        self.assertEqual(ty, sub(v))

    def test_individual_variable_supertype(self) -> None:
        v = IndividualVariable()
        ty = int_type
        sub = ty.constrain_and_bind_variables(v, set(), [])
        self.assertEqual(ty, sub(v))

    def test_attribute_subtype(self) -> None:
        v = IndividualVariable()
        attr_ty = ObjectType(IndividualVariable(), {'__add__': v})
        ty = int_type
        with self.assertRaises(ConcatTypeError):
            attr_ty.constrain_and_bind_variables(ty, set(), [])

    def test_attribute_supertype(self) -> None:
        v = IndividualVariable()
        attr_ty = ObjectType(IndividualVariable(), {'__add__': v})
        ty = int_type
        sub = ty.constrain_and_bind_variables(attr_ty, set(), [])
        self.assertEqual(ty.get_type_of_attribute('__add__'), sub(v))

    def test_py_function_return_subtype(self) -> None:
        v = IndividualVariable()
        py_fun_ty = py_function_type[TypeSequence([int_type]), v]
        ty = int_type.get_type_of_attribute('__add__')
        sub = py_fun_ty.constrain_and_bind_variables(ty, set(), [])
        self.assertEqual(int_type, sub(v))

    def test_py_function_return_supertype(self) -> None:
        v = IndividualVariable()
        py_fun_ty = py_function_type[TypeSequence([int_type]), v]
        ty = int_type.get_type_of_attribute('__add__')
        sub = ty.constrain_and_bind_variables(py_fun_ty, set(), [])
        self.assertEqual(int_type, sub(v))

    def test_type_sequence_subtype(self) -> None:
        v = IndividualVariable()
        seq_ty = TypeSequence([v])
        ty = TypeSequence([int_type])
        sub = seq_ty.constrain_and_bind_variables(ty, set(), [])
        self.assertEqual(int_type, sub(v))

    def test_type_sequence_supertype(self) -> None:
        v = IndividualVariable()
        seq_ty = TypeSequence([v])
        ty = TypeSequence([int_type])
        sub = ty.constrain_and_bind_variables(seq_ty, set(), [])
        self.assertEqual(int_type, sub(v))

    def test_int_addable(self) -> None:
        v = IndividualVariable()
        sub = int_type.constrain_and_bind_variables(
            addable_type[v, v], set(), []
        )
        self.assertEqual(int_type, sub(v))

    def test_int__add__addable__add__(self) -> None:
        v = IndividualVariable()
        int_add = int_type.get_type_of_attribute('__add__')
        addable_add = addable_type[v, v].get_type_of_attribute('__add__')
        sub = int_add.constrain_and_bind_variables(addable_add, set(), [])
        print(v)
        print(int_add)
        print(addable_add)
        print(sub)
        self.assertEqual(int_type, sub(v))


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
