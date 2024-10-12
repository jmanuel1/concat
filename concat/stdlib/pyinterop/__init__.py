"""Concat-Python interoperation helpers."""
from concat.common_types import ConcatFunction
import concat.stdlib.ski
import builtins
import importlib
import os
from typing import (
    Any,
    AsyncContextManager,
    AsyncIterable,
    Callable,
    Iterable,
    Iterator,
    List,
    Mapping,
    Optional,
    Sequence,
    Sized,
    Union,
    cast,
)


def to_py_function(stack: List[object], stash: List[object]) -> None:
    func = cast(Callable[[List[object], List[object]], None], stack.pop())

    def py_func(*args: object) -> object:
        nonlocal stack
        stack += [*args]
        func(stack, stash)
        return stack.pop()

    stack.append(py_func)


def py_call(stack, stash):
    """sequence_of_pairs sequence $function -- return_value"""
    function, sequence, sequence_of_pairs = (
        stack.pop(),
        stack.pop(),
        stack.pop(),
    )
    mapping = dict(sequence_of_pairs)
    stack.append(function(*sequence, **mapping))


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


def getitem(stack: List[object], stash: List[object]) -> None:
    """a i -- a[i]"""
    i = cast(Union[int, slice], stack.pop())
    a = cast(Sequence[object], stack.pop())
    stack.append(a[i])


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
    stack.append(
        cast(str, receiver).encode(cast(str, encoding), cast(str, errors))
    )


def to_bytes(stack: List[object], stash: List[object]) -> None:
    """errors encoding source -- bytes(source, encoding, errors)"""
    source, encoding, errors = (stack.pop() for _ in range(3))
    if errors is None:
        if encoding is None:
            stack.append(bytes(source))  # type: ignore
        else:
            stack.append(bytes(cast(str, source), cast(str, encoding)))
    else:
        stack.append(
            bytes(cast(str, source), cast(str, encoding), cast(str, errors))
        )


def decode_bytes(stack: List[object], stash: List[object]) -> None:
    """errors encoding receiver -- receiver.decode(encoding, errors)"""
    receiver, encoding, errors = (stack.pop() for _ in range(3))
    encoding = 'utf-8' if encoding is None else encoding
    errors = 'strict' if errors is None else errors
    stack.append(
        cast(bytes, receiver).decode(cast(str, encoding), cast(str, errors))
    )


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
        stack.append(
            bytearray(
                cast(str, source), cast(str, encoding), cast(str, errors)
            )
        )


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


def next(stack: List[object], stash: List[object]) -> None:
    """iterator -- next(iterator)"""
    # There is no 'default' parameter because None is a valid default. Code
    # that calls next should catch StopIteration itself to provide a default.
    stack.append(builtins.next(cast(Iterator[object], stack.pop())))


def to_stop_iteration(stack: List[object], stash: List[object]) -> None:
    """value -- StopIteration(value)"""
    stack.append(StopIteration(stack.pop()))


async def with_async(stack: List[object], stash: List[object]) -> None:
    """$body context_manager -- `async with context_manager: body(stack,
    stash)`"""
    context_manager, body = (
        cast(AsyncContextManager, stack.pop()),
        cast(Callable[[List[object], List[object]], None], stack.pop()),
    )
    async with context_manager as val:
        stack.append(val)
        body(stack, stash)


async def for_async(stack: List[object], stash: List[object]) -> None:
    """$body iterable -- `async for target in iterable:` target body"""
    iterable, body = (
        cast(AsyncIterable[object], stack.pop()),
        cast(Callable[[List[object], List[object]], None], stack.pop()),
    )
    async for target in iterable:
        stack.append(target)
        body(stack, stash)


call = concat.stdlib.ski.i


def import_module(stack: List[object], stash: List[object]) -> None:
    """package name -- importlib.import_module(name, package)"""
    stack.append(
        importlib.import_module(
            cast(str, stack.pop()), cast(Optional[str], stack.pop())
        )
    )


def import_advanced(stack: List[object], stash: List[object]) -> None:
    """level fromlist locals globals name -- __import__(name, globals, locals,
    fromlist, level)"""
    name, globals, locals, fromlist, level = (stack.pop() for _ in range(5))
    stack.append(
        __import__(
            cast(str, name),
            cast(Optional[Mapping[str, Any]], globals),
            cast(Optional[Mapping[str, Any]], locals),
            cast(Sequence[str], () if fromlist is None else fromlist),
            0 if level is None else cast(int, level),
        )
    )


def map(stack: List[object], stash: List[object]) -> None:
    'f iterable -- map(f, iterable)'
    iterable = cast(Iterable[object], stack.pop())
    f = cast(ConcatFunction, stack.pop())

    def python_f(x: object) -> object:
        stack.append(x)
        f(stack, stash)
        return stack.pop()

    stack.append(builtins.map(python_f, iterable))


def open(stack: List[object], stash: List[object]) -> None:
    'kwargs -- open(**kwargs)'  # open has a lot of arguments
    stack.append(builtins.open(**cast(Mapping[str, Any], stack.pop())))


def popen(stack: List[object], stash: List[object]) -> None:
    'buffering mode cmd -- subprocess.popen(cmd, mode, buffering)'
    cmd = cast(str, stack.pop())
    mode = cast(Optional[str], stack.pop())
    buffering = cast(Optional[int], stack.pop())
    buffering = -1 if buffering is None else buffering
    stack.append(os.popen(cmd, 'r' if mode is None else mode, buffering))


def fdopen(stack: List[object], stash: List[object]) -> None:
    'kwargs fd -- os.fdopen(fd, **kwargs)'  # fdopen has a lot of arguments
    stack.append(
        os.fdopen(
            cast(int, stack.pop()), **cast(Mapping[str, Any], stack.pop())
        )
    )
