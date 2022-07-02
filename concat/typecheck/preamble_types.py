from concat.typecheck.types import (
    IndividualVariable,
    SequenceVariable,
    ForAll,
    ObjectType,
    StackEffect,
    TypeSequence,
    base_exception_type,
    bool_type,
    context_manager_type,
    dict_type,
    ellipsis_type,
    file_type,
    float_type,
    init_primitives,
    int_type,
    iterable_type,
    list_type,
    module_type,
    none_type,
    no_return_type,
    not_implemented_type,
    object_type,
    optional_type,
    py_function_type,
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
            [
                _rest_var,
                iterable_type[object_type,],
                iterable_type[object_type,],
                py_function_type[TypeSequence([_seq_var]), _a_var],
            ],
            [_rest_var, _a_var],
        ),
    ),
    'swap': ForAll(
        [_rest_var, _a_var, _b_var],
        StackEffect([_rest_var, _a_var, _b_var], [_rest_var, _b_var, _a_var]),
    ),
    'pick': ForAll(
        [_rest_var, _a_var, _b_var, _c_var],
        StackEffect(
            [_rest_var, _a_var, _b_var, _c_var],
            [_rest_var, _a_var, _b_var, _c_var, _a_var],
        ),
    ),
    'nip': ForAll(
        [_rest_var, _a_var],
        StackEffect([_rest_var, object_type, _a_var], [_rest_var, _a_var]),
    ),
    'nip_2': ObjectType(
        _a_var,
        {
            '__call__': StackEffect(
                [_rest_var, object_type, object_type, _b_var],
                [_rest_var, _b_var],
            )
        },
        [_rest_var, _b_var],
    ),
    'drop': ForAll(
        [_rest_var], StackEffect([_rest_var, object_type], [_rest_var])
    ),
    'dup': ForAll(
        [_rest_var, _a_var],
        StackEffect([_rest_var, _a_var], [_rest_var, _a_var, _a_var]),
    ),
    'open': ForAll(
        [_rest_var],
        StackEffect([_rest_var, dict_type, str_type], [_rest_var, file_type]),
    ),
    'over': ForAll(
        [_rest_var, _a_var, _b_var],
        StackEffect(
            [_rest_var, _a_var, _b_var], [_rest_var, _a_var, _b_var, _a_var]
        ),
    ),
    'to_list': ForAll(
        [_rest_var],
        StackEffect([_rest_var, iterable_type], [_rest_var, list_type]),
    ),
    'False': ForAll(
        [_rest_var], StackEffect([_rest_var], [_rest_var, bool_type])
    ),
    'curry': ForAll(
        [_rest_var, _seq_var, _stack_var, _a_var],
        StackEffect(
            [_rest_var, _a_var, StackEffect([_seq_var, _a_var], [_stack_var])],
            [_rest_var, StackEffect([_seq_var], [_stack_var])],
        ),
    ),
    'choose': ForAll(
        [_rest_var, _seq_var],
        StackEffect(
            [
                _rest_var,
                bool_type,
                StackEffect([_rest_var], [_seq_var]),
                StackEffect([_rest_var], [_seq_var]),
            ],
            [_seq_var],
        ),
    ),
    'if_not': ForAll(
        [_rest_var],
        StackEffect(
            [_rest_var, bool_type, StackEffect([_rest_var], [_rest_var])],
            [_rest_var],
        ),
    ),
    # Python builtins
    'print': py_function_type,
    'Exception': py_function_type,
    'input': py_function_type,
    'if_then': ObjectType(
        _x,
        {
            '__call__': StackEffect(
                [_rest_var, bool_type, StackEffect([_rest_var], [_rest_var])],
                [_rest_var],
            )
        },
        [_rest_var],
    ),
    'call': ObjectType(
        _x,
        {
            '__call__': StackEffect(
                [_rest_var, StackEffect([_rest_var], [_seq_var])], [_seq_var],
            )
        },
        [_rest_var, _seq_var],
    ),
    'True': ObjectType(
        _a_var,
        {'__call__': StackEffect([_rest_var], [_rest_var, bool_type])},
        [_rest_var],
    ),
    # TODO: Separate type-check-time environment from runtime environment.
    # XXX: generalize to_int over the stack
    'to_int': StackEffect(
        TypeSequence([_stack_type_var, optional_type[int_type,], object_type]),
        TypeSequence([_stack_type_var, int_type]),
    ),
    'tuple': tuple_type,
    'BaseException': base_exception_type,
    'NoReturn': no_return_type,
    'subscriptable': subscriptable_type,
    'subtractable': subtractable_type,
    'bool': bool_type,
    'object': object_type,
    'context_manager': context_manager_type,
    'dict': dict_type,
    'module': module_type,
    'list': list_type,
    'str': str_type,
    'py_function': py_function_type,
    'Optional': optional_type,
    'int': int_type,
    'float': float_type,
    'file': file_type,
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
}
