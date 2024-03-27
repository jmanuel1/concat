from concat.typecheck.types import (
    IndividualVariable,
    SequenceVariable,
    ForAll,
    ObjectType,
    StackEffect,
    TypeSequence,
    addable_type,
    base_exception_type,
    bool_type,
    context_manager_type,
    dict_type,
    ellipsis_type,
    file_type,
    float_type,
    geq_comparable_type,
    init_primitives,
    int_type,
    iterable_type,
    iterator_type,
    leq_comparable_type,
    lt_comparable_type,
    list_type,
    module_type,
    none_type,
    no_return_type,
    not_implemented_type,
    object_type,
    optional_type,
    py_function_type,
    py_overloaded_type,
    str_type,
    subscriptable_type,
    subtractable_type,
    tuple_type,
)

init_primitives()

_rest_var = SequenceVariable()
_seq_var = SequenceVariable()
_stack_var = SequenceVariable()
_stack_type_var = SequenceVariable()
_a_var = IndividualVariable()
_b_var = IndividualVariable()
_c_var = IndividualVariable()
_x = IndividualVariable()

types = {
    'py_call': ForAll(
        [_rest_var, _seq_var, _a_var],
        StackEffect(
            TypeSequence(
                [
                    _rest_var,
                    iterable_type[object_type,],
                    iterable_type[object_type,],
                    py_function_type[TypeSequence([_seq_var]), _a_var],
                ]
            ),
            TypeSequence([_rest_var, _a_var]),
        ),
    ),
    'swap': ForAll(
        [_rest_var, _a_var, _b_var],
        StackEffect(
            TypeSequence([_rest_var, _a_var, _b_var]),
            TypeSequence([_rest_var, _b_var, _a_var]),
        ),
    ),
    'pick': ForAll(
        [_rest_var, _a_var, _b_var, _c_var],
        StackEffect(
            TypeSequence([_rest_var, _a_var, _b_var, _c_var]),
            TypeSequence([_rest_var, _a_var, _b_var, _c_var, _a_var]),
        ),
    ),
    'nip': ForAll(
        [_rest_var, _a_var],
        StackEffect(
            TypeSequence([_rest_var, object_type, _a_var]),
            TypeSequence([_rest_var, _a_var]),
        ),
    ),
    'nip_2': ObjectType(
        _a_var,
        {
            '__call__': StackEffect(
                TypeSequence([_rest_var, object_type, object_type, _b_var]),
                TypeSequence([_rest_var, _b_var]),
            )
        },
        [_rest_var, _b_var],
    ),
    'drop': ForAll(
        [_rest_var],
        StackEffect(
            TypeSequence([_rest_var, object_type]), TypeSequence([_rest_var])
        ),
    ),
    'dup': ForAll(
        [_rest_var, _a_var],
        StackEffect(
            TypeSequence([_rest_var, _a_var]),
            TypeSequence([_rest_var, _a_var, _a_var]),
        ),
    ),
    'open': ForAll(
        [_rest_var],
        StackEffect(
            TypeSequence(
                [_rest_var, dict_type[str_type, object_type], str_type]
            ),
            TypeSequence([_rest_var, file_type]),
        ),
    ),
    'over': ForAll(
        [_rest_var, _a_var, _b_var],
        StackEffect(
            TypeSequence([_rest_var, _a_var, _b_var]),
            TypeSequence([_rest_var, _a_var, _b_var, _a_var]),
        ),
    ),
    'to_list': ForAll(
        [_rest_var],
        StackEffect(
            TypeSequence([_rest_var, iterable_type[_a_var,]]),
            TypeSequence([_rest_var, list_type[_a_var,]]),
        ),
    ),
    'False': ForAll(
        [_rest_var],
        StackEffect(
            TypeSequence([_rest_var]), TypeSequence([_rest_var, bool_type])
        ),
    ),
    'curry': ForAll(
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
    'choose': ForAll(
        [_rest_var, _seq_var],
        StackEffect(
            TypeSequence(
                [
                    _rest_var,
                    bool_type,
                    StackEffect(
                        TypeSequence([_rest_var]), TypeSequence([_seq_var])
                    ),
                    StackEffect(
                        TypeSequence([_rest_var]), TypeSequence([_seq_var])
                    ),
                ]
            ),
            TypeSequence([_seq_var]),
        ),
    ),
    'if_not': ForAll(
        [_rest_var],
        StackEffect(
            TypeSequence(
                [
                    _rest_var,
                    bool_type,
                    StackEffect(
                        TypeSequence([_rest_var]), TypeSequence([_rest_var])
                    ),
                ]
            ),
            TypeSequence([_rest_var]),
        ),
    ),
    'if_then': ObjectType(
        _x,
        {
            '__call__': StackEffect(
                TypeSequence(
                    [
                        _rest_var,
                        bool_type,
                        StackEffect(
                            TypeSequence([_rest_var]),
                            TypeSequence([_rest_var]),
                        ),
                    ]
                ),
                TypeSequence([_rest_var]),
            )
        },
        [_rest_var],
    ),
    'call': ObjectType(
        _x,
        {
            '__call__': StackEffect(
                TypeSequence(
                    [
                        _rest_var,
                        StackEffect(
                            TypeSequence([_rest_var]), TypeSequence([_seq_var])
                        ),
                    ]
                ),
                TypeSequence([_seq_var]),
            )
        },
        [_rest_var, _seq_var],
    ),
    'loop': ForAll(
        [_rest_var],
        StackEffect(
            TypeSequence(
                [
                    _rest_var,
                    StackEffect(
                        TypeSequence([_rest_var]),
                        TypeSequence([_rest_var, bool_type]),
                    ),
                ]
            ),
            TypeSequence([_rest_var]),
        ),
    ),
    'True': ObjectType(
        _a_var,
        {
            '__call__': StackEffect(
                TypeSequence([_rest_var]), TypeSequence([_rest_var, bool_type])
            )
        },
        [_rest_var],
    ),
    # TODO: Separate type-check-time environment from runtime environment.
    # XXX: generalize to_int over the stack
    'to_int': StackEffect(
        TypeSequence([_stack_type_var, optional_type[int_type,], object_type]),
        TypeSequence([_stack_type_var, int_type]),
    ),
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
    'file': file_type,
    'none': none_type,
    'None': ForAll(
        [_stack_type_var],
        StackEffect(
            TypeSequence([_stack_type_var]),
            TypeSequence([_stack_type_var, none_type]),
        ),
    ),
    '...': ForAll(
        [_stack_type_var],
        StackEffect(
            TypeSequence([_stack_type_var]),
            TypeSequence([_stack_type_var, ellipsis_type]),
        ),
    ),
    'Ellipsis': ForAll(
        [_stack_type_var],
        StackEffect(
            TypeSequence([_stack_type_var]),
            TypeSequence([_stack_type_var, ellipsis_type]),
        ),
    ),
    'NotImplemented': ForAll(
        [_stack_type_var],
        StackEffect(
            TypeSequence([_stack_type_var]),
            TypeSequence([_stack_type_var, not_implemented_type]),
        ),
    ),
    # Addition type rules:
    # require object_type because the methods should return
    # NotImplemented for most types
    # FIXME: Make the rules safer... somehow
    # ... a b => (... {__add__(object) -> s} t)
    # ---
    # a b + => (... s)
    # ... a b => (... t {__radd__(object) -> s})
    # ---
    # a b + => (... s)
    # FIXME: Implement the second type rule
    '+': ForAll(
        [_stack_type_var, _c_var],
        StackEffect(
            TypeSequence(
                [_stack_type_var, addable_type[_c_var,], object_type]
            ),
            TypeSequence([_stack_type_var, _c_var]),
        ),
    ),
    # FIXME: We should check if the other operand supports __rsub__ if the
    # first operand doesn't support __sub__.
    '-': ForAll(
        [_stack_type_var, _b_var, _c_var],
        StackEffect(
            TypeSequence(
                [_stack_type_var, subtractable_type[_b_var, _c_var], _b_var]
            ),
            TypeSequence([_stack_type_var, _c_var]),
        ),
    ),
    # Rule 1: first operand has __ge__(type(second operand))
    # Rule 2: second operand has __le__(type(first operand))
    # FIXME: Implement the second type rule
    '>=': ForAll(
        [_stack_type_var, _b_var],
        StackEffect(
            TypeSequence(
                [_stack_type_var, geq_comparable_type[_b_var,], _b_var]
            ),
            TypeSequence([_stack_type_var, bool_type]),
        ),
    ),
    # Rule 1: first operand has __lt__(type(second operand))
    # Rule 2: second operand has __gt__(type(first operand))
    # FIXME: Implement the second type rule
    # Also look at Python's note about when reflected method get's priority.
    '<': ForAll(
        [_stack_type_var, _b_var],
        StackEffect(
            TypeSequence(
                [_stack_type_var, lt_comparable_type[_b_var,], _b_var]
            ),
            TypeSequence([_stack_type_var, bool_type]),
        ),
    ),
    # FIXME: Implement the second type rule
    '<=': ForAll(
        [_stack_type_var, _b_var],
        StackEffect(
            TypeSequence(
                [_stack_type_var, leq_comparable_type[_b_var,], _b_var]
            ),
            TypeSequence([_stack_type_var, bool_type]),
        ),
    ),
    'is': ForAll(
        [_stack_type_var],
        StackEffect(
            TypeSequence([_stack_type_var, object_type, object_type]),
            TypeSequence([_stack_type_var, bool_type]),
        ),
    ),
    'and': ForAll(
        [_stack_type_var],
        StackEffect(
            TypeSequence([_stack_type_var, object_type, object_type]),
            TypeSequence([_stack_type_var, bool_type]),
        ),
    ),
    'or': ForAll(
        [_stack_type_var],
        StackEffect(
            TypeSequence([_stack_type_var, object_type, object_type]),
            TypeSequence([_stack_type_var, bool_type]),
        ),
    ),
    # TODO: I should be more careful here, since at least __eq__ can be
    # deleted, if I remember correctly.
    '==': ForAll(
        [_stack_type_var],
        StackEffect(
            TypeSequence([_stack_type_var, object_type, object_type]),
            TypeSequence([_stack_type_var, bool_type]),
        ),
    ),
}
