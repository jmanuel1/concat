"""Concat-Python interoperation helpers."""
from typing import List


def to_int(stack: List[object], stash: List[object]) -> None:
    """base x -- int(x, base=base)"""
    x, base = stack.pop(), stack.pop()
    # we check if base is None so that base can be optional
    # int(x, base=None) raises a TypeError
    if base is None:
        stack.append(int(x))  # type: ignore
    else:
        stack.append(int(x, base=base))  # type: ignore
