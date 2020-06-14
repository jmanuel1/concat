from concat.level1.typecheck import (
    IndividualVariable,
    SequenceVariable,
    ForAll,
    StackEffect,
    PrimitiveTypes,
    PrimitiveInterfaces
)


_rest_var = SequenceVariable()
_seq_var = SequenceVariable()
_stack_var = SequenceVariable()
_a_var = IndividualVariable()
_b_var = IndividualVariable()
_c_var = IndividualVariable()

types = {
    'py_call': ForAll(
        [_rest_var],
        StackEffect([
            _rest_var,
            PrimitiveInterfaces.iterable,
            PrimitiveInterfaces.iterable,
            PrimitiveTypes.py_function
        ], [
            _rest_var,
            PrimitiveTypes.object
        ])
    ),
    'swap': ForAll(
        [_rest_var, _a_var, _b_var],
        StackEffect([
            _rest_var,
            _a_var,
            _b_var
        ], [
            _rest_var,
            _b_var,
            _a_var
        ])
    ),
    'pick': ForAll(
        [_rest_var, _a_var, _b_var, _c_var],
        StackEffect([
            _rest_var,
            _a_var,
            _b_var,
            _c_var
        ], [
            _rest_var,
            _a_var,
            _b_var,
            _c_var,
            _a_var
        ])
    ),
    'nip': ForAll(
        [_rest_var, _a_var],
        StackEffect([
            _rest_var,
            PrimitiveTypes.object,
            _a_var
        ], [
            _rest_var,
            _a_var
        ])
    ),
    'drop': ForAll(
        [_rest_var],
        StackEffect([
            _rest_var,
            PrimitiveTypes.object
        ], [
            _rest_var
        ])
    ),
    'dup': ForAll(
        [_rest_var, _a_var],
        StackEffect([
            _rest_var,
            _a_var
        ], [
            _rest_var,
            _a_var,
            _a_var
        ])
    ),
    'open': ForAll(
        [_rest_var],
        StackEffect([
            _rest_var,
            PrimitiveTypes.dict,
            PrimitiveTypes.str
        ], [
            _rest_var,
            PrimitiveTypes.file
        ])
    ),
    'over': ForAll(
        [_rest_var, _a_var, _b_var],
        StackEffect([
            _rest_var,
            _a_var,
            _b_var
        ], [
            _rest_var,
            _a_var,
            _b_var,
            _a_var
        ])
    ),
    'to_list': ForAll(
        [_rest_var],
        StackEffect([
            _rest_var,
            PrimitiveInterfaces.iterable
        ], [
            _rest_var,
            PrimitiveTypes.list
        ])
    ),
    'False': ForAll(
        [_rest_var],
        StackEffect([
            _rest_var
        ], [
            _rest_var,
            PrimitiveTypes.bool
        ])
    ),
    'curry': ForAll(
        [_rest_var, _seq_var, _stack_var, _a_var],
        StackEffect([
            _rest_var,
            _a_var,
            StackEffect([_seq_var, _a_var], [_stack_var])
        ], [
            _rest_var,
            StackEffect([_seq_var], [_stack_var])
        ])
    ),
    'choose': ForAll(
        [_rest_var, _seq_var],
        StackEffect([
            _rest_var,
            PrimitiveTypes.bool,
            StackEffect([_rest_var], [_seq_var]),
            StackEffect([_rest_var], [_seq_var])
        ], [
            _seq_var
        ])
    ),
    'if_not': ForAll(
        [_rest_var],
        StackEffect([
            _rest_var,
            PrimitiveTypes.bool,
            StackEffect([_rest_var], [_rest_var])
        ], [
            _rest_var
        ])
    ),
    # Python builtins
    'print': PrimitiveTypes.py_function,
    'Exception': PrimitiveTypes.py_function,
    'input': PrimitiveTypes.py_function
}
