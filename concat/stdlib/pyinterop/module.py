import sys
import types
import concat.stdlib.importlib
from typing import List, Callable, cast

# make this module callable
sys.modules[__name__].__class__ = concat.stdlib.importlib.Module


def doc(stack: List[object], stash: List[object]) -> None:
    """$mod -- $mod$.__doc__"""
    stack.append(stack.pop().__doc__)


def name(stack: List[object], stash: List[object]) -> None:
    """$mod -- $mod$.__name__"""
    stack.append(cast(types.ModuleType, stack.pop()).__name__)


def annotations(stack: List[object], stash: List[object]) -> None:
    """$mod -- $mod$.__annotations__"""
    stack.append(cast(types.ModuleType, stack.pop()).__annotations__)


def file(stack: List[object], stash: List[object]) -> None:
    """$mod -- $mod$.__file__"""
    stack.append(cast(types.ModuleType, stack.pop()).__file__)


def dict(stack: List[object], stash: List[object]) -> None:
    """$mod -- $mod$.__dict__"""
    stack.append(cast(types.ModuleType, stack.pop()).__dict__)
