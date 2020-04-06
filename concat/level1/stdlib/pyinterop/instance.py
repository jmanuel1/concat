import sys
import types
import concat.level0.stdlib.importlib
from typing import List, Callable, cast

# make this module callable
sys.modules[__name__].__class__ = concat.level0.stdlib.importlib.Module


def dict(stack: List[object], stash: List[object]) -> None:
    """$inst -- $inst$.__dict__"""
    stack.append(stack.pop().__dict__)


def cls(stack: List[object], stash: List[object]) -> None:
    """$inst -- $inst$.__class__"""
    stack.append(stack.pop().__class__)
