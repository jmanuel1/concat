from concat.level1.typecheck.types import (
    IndividualVariable,
    SequenceVariable,
    ForAll,
    StackEffect,
    PrimitiveInterfaces,
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

types = {
    'py_call': ForAll(
        [_rest_var],
        StackEffect(
            [
                _rest_var,
                PrimitiveInterfaces.iterable,
                PrimitiveInterfaces.iterable,
                py_function_type,
            ],
            [_rest_var, object_type],
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
        StackEffect(
            [_rest_var, PrimitiveInterfaces.iterable], [_rest_var, list_type]
        ),
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
    'file': PrimitiveTypes.file
}
