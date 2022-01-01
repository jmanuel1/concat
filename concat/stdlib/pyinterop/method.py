import sys
import types
import concat.stdlib.importlib
from typing import List, Callable, cast

# make this module callable
sys.modules[__name__].__class__ = concat.stdlib.importlib.Module


def self(stack: List[object], stash: List[object]) -> None:
    """$method -- $method$.__self__"""
    stack.append(cast(types.MethodType, stack.pop()).__self__)


def func(stack: List[object], stash: List[object]) -> None:
    """$method -- $method$.__func__"""
    stack.append(cast(types.MethodType, stack.pop()).__func__)


def doc(stack: List[object], stash: List[object]) -> None:
    """$method -- $method$.__doc__"""
    stack.append(stack.pop().__doc__)


def name(stack: List[object], stash: List[object]) -> None:
    """$method -- $method$.__name__"""
    stack.append(cast(Callable, stack.pop()).__name__)


def module(stack: List[object], stash: List[object]) -> None:
    """$method -- $method$.__module__"""
    stack.append(stack.pop().__module__)
