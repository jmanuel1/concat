"""Concat-Python interoperation helpers."""


def py_call(stack, stash):
    """sequence_of_pairs sequence $function -- return_value"""
    function, sequence, sequence_of_pairs = stack.pop(), stack.pop(), stack.pop()
    mapping = dict(sequence_of_pairs)
    stack.append(function(*sequence, **mapping))
