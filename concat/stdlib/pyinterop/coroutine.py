import sys
import types
import concat.stdlib.importlib
from typing import List, Callable, cast, Coroutine, Type, Optional

# make this module callable
sys.modules[__name__].__class__ = concat.stdlib.importlib.Module


def send(stack: List[object], stash: List[object]) -> None:
    """value coroutine -- coroutine.send(value)"""
    stack.append(cast(Coroutine, stack.pop()).send(stack.pop()))


def throw(stack: List[object], stash: List[object]) -> None:
    """traceback value type coroutine -- coroutine.throw(type, value, traceback)"""
    coroutine = stack.pop()
    type = cast(Type[BaseException], stack.pop())
    value, traceback = (stack.pop() for _ in range(2))
    stack.append(
        cast(Coroutine, coroutine).throw(
            type,
            None if value is None else type(value),
            cast(Optional[types.TracebackType], traceback),
        )
    )


def close(stack: List[object], stash: List[object]) -> None:
    """coroutine --"""
    coroutine = cast(Coroutine, stack.pop())
    coroutine.close()
