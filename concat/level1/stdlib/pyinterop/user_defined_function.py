import sys
import types
import concat.level0.stdlib.importlib
from typing import List, Callable, cast

# make this module callable
sys.modules[__name__].__class__ = concat.level0.stdlib.importlib.Module


def doc(stack: List[object], stash: List[object]) -> None:
    """$fun -- $fun$.__doc__"""
    stack.append(stack.pop().__doc__)


def name(stack: List[object], stash: List[object]) -> None:
    """$fun -- $fun$.__name__"""
    stack.append(cast(Callable, stack.pop()).__name__)


def qualname(stack: List[object], stash: List[object]) -> None:
    """$fun -- $fun$.__qualname__"""
    stack.append(cast(Callable, stack.pop()).__qualname__)


def module(stack: List[object], stash: List[object]) -> None:
    """$fun -- $fun$.__module__"""
    stack.append(stack.pop().__module__)


def defaults(stack: List[object], stash: List[object]) -> None:
    """$fun -- $fun$.__defaults__"""
    stack.append(stack.pop().__defaults__)  # type: ignore


def code(stack: List[object], stash: List[object]) -> None:
    """$fun -- $fun$.__code__"""
    stack.append(stack.pop().__code__)  # type: ignore


def globals(stack: List[object], stash: List[object]) -> None:
    """$fun -- $fun$.__globals__"""
    stack.append(stack.pop().__globals__)  # type: ignore


def dict(stack: List[object], stash: List[object]) -> None:
    """$fun -- $fun$.__dict__"""
    stack.append(stack.pop().__dict__)


def closure(stack: List[object], stash: List[object]) -> None:
    """$fun -- $fun$.__closure__"""
    stack.append(cast(types.FunctionType, stack.pop()).__closure__)


def annotations(stack: List[object], stash: List[object]) -> None:
    """$fun -- $fun$.__annotations__"""
    stack.append(stack.pop().__annotations__)


def kwdefaults(stack: List[object], stash: List[object]) -> None:
    """$fun -- $fun$.__kwdefaults__"""
    stack.append(cast(types.FunctionType, stack.pop()).__kwdefaults__)
