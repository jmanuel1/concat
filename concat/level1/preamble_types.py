from concat.level1.typecheck.types import (
    IndividualVariable,
    SequenceVariable,
    ForAll,
    StackEffect,
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
    # FIXME: Types should be universally quantified.
    'if_then': StackEffect(
        [_rest_var, bool_type, StackEffect([_rest_var], [_rest_var])],
        [_rest_var],
    ),
    'call': StackEffect(
        [_rest_var, StackEffect([_rest_var], [_seq_var])], [_seq_var],
    ),
}
