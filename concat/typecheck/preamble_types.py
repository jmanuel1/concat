from concat.typecheck.types import (
    BoundVariable,
    GenericType,
    ItemKind,
    ObjectType,
    TypeSequence,
    addable_type,
    context_manager_type,
    geq_comparable_type,
    iterable_type,
    iterator_type,
    leq_comparable_type,
    lt_comparable_type,
    no_return_type,
    optional_type,
    py_function_type,
    py_overloaded_type,
    subscriptable_type,
    subtractable_type,
)


_a_var = BoundVariable(ItemKind)

types = {
    'addable': addable_type,
    'leq_comparable': leq_comparable_type,
    'lt_comparable': lt_comparable_type,
    'geq_comparable': geq_comparable_type,
    # TODO: Separate type-check-time environment from runtime environment.
    'iterable': iterable_type,
    'NoReturn': no_return_type,
    'subscriptable': subscriptable_type,
    'subtractable': subtractable_type,
    'context_manager': context_manager_type,
    'iterator': iterator_type,
    'py_function': py_function_type,
    'py_overloaded': py_overloaded_type,
    'Optional': optional_type,
    'SupportsAbs': GenericType(
        [_a_var],
        ObjectType({'__abs__': py_function_type[TypeSequence([]), _a_var],},),
    ),
}
