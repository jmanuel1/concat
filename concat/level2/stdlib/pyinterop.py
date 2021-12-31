from typing import List, Callable, cast
from concat.typecheck.types import (
    ForAll,
    StackEffect,
    SequenceVariable,
    py_function_type,
)


_rest_var = SequenceVariable()
_rest_var_2 = SequenceVariable()
_rest_var_3 = SequenceVariable()


globals()['@@types'] = {
    'to_py_function': ForAll(
        [_rest_var, _rest_var_2, _rest_var_3],
        StackEffect(
            [_rest_var, StackEffect([_rest_var_2], [_rest_var_3])],
            [_rest_var, py_function_type],
        ),
    )
}


def to_py_function(stack: List[object], stash: List[object]) -> None:
    func = cast(Callable[[List[object], List[object]], None], stack.pop())

    def py_func(*args: object) -> object:
        nonlocal stack
        stack += [*args]
        func(stack, stash)
        return stack.pop()

    stack.append(py_func)
