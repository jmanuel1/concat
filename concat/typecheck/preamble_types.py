from concat.typecheck.types import (
    GenericType,
    IndividualVariable,
    SequenceVariable,
    StackEffect,
    TypeSequence,
    addable_type,
    context_manager_type,
    ellipsis_type,
    geq_comparable_type,
    iterable_type,
    iterator_type,
    leq_comparable_type,
    lt_comparable_type,
    module_type,
    no_return_type,
    none_type,
    not_implemented_type,
    optional_type,
    py_function_type,
    py_overloaded_type,
    subscriptable_type,
    subtractable_type,
)


_rest_var = SequenceVariable()
_seq_var = SequenceVariable()
_stack_var = SequenceVariable()
_stack_type_var = SequenceVariable()
_a_var = IndividualVariable()
_b_var = IndividualVariable()
_c_var = IndividualVariable()
_x = IndividualVariable()

types = {
    'addable': addable_type,
    'leq_comparable': leq_comparable_type,
    'lt_comparable': lt_comparable_type,
    'geq_comparable': geq_comparable_type,
    'swap': GenericType(
        [_rest_var, _a_var, _b_var],
        StackEffect(
            TypeSequence([_rest_var, _a_var, _b_var]),
            TypeSequence([_rest_var, _b_var, _a_var]),
        ),
    ),
    'pick': GenericType(
        [_rest_var, _a_var, _b_var, _c_var],
        StackEffect(
            TypeSequence([_rest_var, _a_var, _b_var, _c_var]),
            TypeSequence([_rest_var, _a_var, _b_var, _c_var, _a_var]),
        ),
    ),
    'dup': GenericType(
        [_rest_var, _a_var],
        StackEffect(
            TypeSequence([_rest_var, _a_var]),
            TypeSequence([_rest_var, _a_var, _a_var]),
        ),
    ),
    'over': GenericType(
        [_rest_var, _a_var, _b_var],
        StackEffect(
            TypeSequence([_rest_var, _a_var, _b_var]),
            TypeSequence([_rest_var, _a_var, _b_var, _a_var]),
        ),
    ),
    'curry': GenericType(
        [_rest_var, _seq_var, _stack_var, _a_var],
        StackEffect(
            TypeSequence(
                [
                    _rest_var,
                    _a_var,
                    StackEffect(
                        TypeSequence([_seq_var, _a_var]),
                        TypeSequence([_stack_var]),
                    ),
                ]
            ),
            TypeSequence(
                [
                    _rest_var,
                    StackEffect(
                        TypeSequence([_seq_var]), TypeSequence([_stack_var])
                    ),
                ]
            ),
        ),
    ),
    'call': GenericType(
        [_rest_var, _seq_var],
        StackEffect(
            TypeSequence(
                [
                    _rest_var,
                    StackEffect(
                        TypeSequence([_rest_var]), TypeSequence([_seq_var])
                    ),
                ]
            ),
            TypeSequence([_seq_var]),
        ),
    ),
    # TODO: Separate type-check-time environment from runtime environment.
    'iterable': iterable_type,
    'NoReturn': no_return_type,
    'subscriptable': subscriptable_type,
    'subtractable': subtractable_type,
    'context_manager': context_manager_type,
    'iterator': iterator_type,
    'module': module_type,
    'py_function': py_function_type,
    'py_overloaded': py_overloaded_type,
    'Optional': optional_type,
    'none': none_type,
    'None': GenericType(
        [_stack_type_var],
        StackEffect(
            TypeSequence([_stack_type_var]),
            TypeSequence([_stack_type_var, none_type]),
        ),
    ),
    '...': GenericType(
        [_stack_type_var],
        StackEffect(
            TypeSequence([_stack_type_var]),
            TypeSequence([_stack_type_var, ellipsis_type]),
        ),
    ),
    'Ellipsis': GenericType(
        [_stack_type_var],
        StackEffect(
            TypeSequence([_stack_type_var]),
            TypeSequence([_stack_type_var, ellipsis_type]),
        ),
    ),
    'NotImplemented': GenericType(
        [_stack_type_var],
        StackEffect(
            TypeSequence([_stack_type_var]),
            TypeSequence([_stack_type_var, not_implemented_type]),
        ),
    ),
}
