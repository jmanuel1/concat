from concat.level1.typecheck.types import (
    IndividualVariable,
    SequenceVariable,
    ForAll,
    StackEffect,
    ObjectType,
    bool_type,
    dict_type,
    file_type,
    init_primitives,
    list_type,
    object_type,
    py_function_type,
    str_type,
)

init_primitives()

_rest_var = SequenceVariable()
_seq_var = SequenceVariable()
_stack_var = SequenceVariable()
_a_var = IndividualVariable()
_b_var = IndividualVariable()
_c_var = IndividualVariable()
_x = IndividualVariable()

types = {
    'if_then': ObjectType(_x, {'__call__': StackEffect(
        [_rest_var, bool_type, StackEffect([_rest_var], [_rest_var])],
        [_rest_var],
    )}, [_rest_var]),
    'call': ObjectType(_x, {'__call__': StackEffect(
        [_rest_var, StackEffect([_rest_var], [_seq_var])], [_seq_var],
    )}, [_rest_var, _seq_var]),
    'True': ObjectType(
        _a_var,
        {
            '__call__': StackEffect([_rest_var], [_rest_var, bool_type])
        },
        [_rest_var]
    ),
}
