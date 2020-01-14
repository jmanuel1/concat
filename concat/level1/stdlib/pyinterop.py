"""Concat-Python interoperation helpers."""
from typing import List, cast, Sized, Sequence, Union, Iterable, Mapping
import builtins


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


def len(stack: List[object], stash: List[object]) -> None:
    """s -- len(s)"""
    stack.append(builtins.len(cast(Sized, stack.pop())))
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


def ord(stack: List[object], stash: List[object]) -> None:
    """c -- ord(c)"""
    stack.append(builtins.ord(cast(Union[str, bytes], stack.pop())))


def chr(stack: List[object], stash: List[object]) -> None:
    """i -- chr(i)"""
    stack.append(builtins.chr(cast(int, stack.pop())))


def encode_str(stack: List[object], stash: List[object]) -> None:
    """errors encoding receiver -- receiver.encode(encoding, errors)"""
    receiver, encoding, errors = (stack.pop() for _ in range(3))
    encoding = 'utf-8' if encoding is None else encoding
    errors = 'strict' if errors is None else errors
    stack.append(cast(str, receiver).encode(
        cast(str, encoding), cast(str, errors)))


def to_bytes(stack: List[object], stash: List[object]) -> None:
    """errors encoding source -- bytes(source, encoding, errors)"""
    source, encoding, errors = (stack.pop() for _ in range(3))
    if errors is None:
        if encoding is None:
            stack.append(bytes(source))  # type: ignore
        else:
            stack.append(bytes(cast(str, source), cast(str, encoding)))
    else:
        stack.append(bytes(cast(str, source), cast(
            str, encoding), cast(str, errors)))


def decode_bytes(stack: List[object], stash: List[object]) -> None:
    """errors encoding receiver -- receiver.decode(encoding, errors)"""
    receiver, encoding, errors = (stack.pop() for _ in range(3))
    encoding = 'utf-8' if encoding is None else encoding
    errors = 'strict' if errors is None else errors
    stack.append(cast(bytes, receiver).decode(
        cast(str, encoding), cast(str, errors)))


def to_tuple(stack: List[object], stash: List[object]) -> None:
    """iterable -- tuple(iterable)"""
    iterable = cast(Iterable[object], stack.pop())
    stack.append(tuple(() if iterable is None else iterable))


def to_list(stack: List[object], stash: List[object]) -> None:
    """iterable -- list(iterable)"""
    iterable = cast(Iterable[object], stack.pop())
    stack.append(list([] if iterable is None else iterable))


def to_bytearray(stack: List[object], stash: List[object]) -> None:
    """errors encoding source -- bytearray(source, encoding, errors)"""
    source, encoding, errors = (stack.pop() for _ in range(3))
    if errors is None:
        if encoding is None:
            stack.append(bytearray(source))  # type: ignore
        else:
            stack.append(bytearray(cast(str, source), cast(str, encoding)))
    else:
        stack.append(bytearray(cast(str, source), cast(
            str, encoding), cast(str, errors)))


def to_set(stack: List[object], stash: List[object]) -> None:
    """iterable -- set(iterable)"""
    iterable = stack.pop()
    if iterable is None:
        stack.append(set())
    else:
        stack.append(set(cast(Iterable[object], iterable)))


def add_to_set(stack: List[object], stash: List[object]) -> None:
    """elem receiver -- receiver.add(elem)"""
    receiver, elem = (stack.pop() for _ in range(2))
    cast(set, receiver).add(elem)


def to_frozenset(stack: List[object], stash: List[object]) -> None:
    """iterable -- frozenset(iterable)"""
    iterable = stack.pop()
    if iterable is None:
        stack.append(frozenset())
    else:
        stack.append(frozenset(cast(Iterable[object], iterable)))


def to_dict(stack: List[object], stash: List[object]) -> None:
    """iterable -- dict(iterable)"""
    iterable = stack.pop()
    if iterable is None:
        stack.append({})
    else:
        stack.append(dict(cast(Union[Mapping, Iterable], iterable)))
