import sys
import types
import concat.stdlib.importlib
from typing import List, Callable, cast

# make this module callable
sys.modules[__name__].__class__ = concat.stdlib.importlib.Module


def self(stack: List[object], stash: List[object]) -> None:
    """$fun -- $fun$.__self__"""
    stack.append(cast(types.BuiltinFunctionType, stack.pop()).__self__)


def doc(stack: List[object], stash: List[object]) -> None:
    """$fun -- $fun$.__doc__"""
    stack.append(stack.pop().__doc__)


def name(stack: List[object], stash: List[object]) -> None:
    """$fun -- $fun$.__name__"""
    stack.append(cast(Callable, stack.pop()).__name__)


def module(stack: List[object], stash: List[object]) -> None:
    """$fun -- $fun$.__module__"""
    stack.append(stack.pop().__module__)
