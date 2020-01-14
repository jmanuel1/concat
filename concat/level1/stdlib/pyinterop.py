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


def to_bool(stack: List[object], stash: List[object]) -> None:
    """x -- bool(x)"""
    stack.append(bool(stack.pop()))


def to_float(stack: List[object], stash: List[object]) -> None:
    """x -- float(x)"""
    stack.append(float(stack.pop()))  # type: ignore


def to_complex(stack: List[object], stash: List[object]) -> None:
    """imag real -- complex(real, imag)"""
    real, imag = stack.pop(), stack.pop()
    if imag is None:
        stack.append(complex(real))  # type: ignore
    else:
        stack.append(complex(real, imag))  # type: ignore


def to_slice(stack: List[object], stash: List[object]) -> None:
    """step stop start -- slice(start, stop, step)"""
    stack.append(slice(stack.pop(), stack.pop(), stack.pop()))


def to_str(stack: List[object], stash: List[object]) -> None:
    """errors encoding object -- str(object, encoding, errors)"""
    object, encoding, errors = (stack.pop() for _ in range(3))
    if encoding is None and errors is None:
        stack.append(str(object))
    else:
        stack.append(str(object, encoding, errors))  # type: ignore
