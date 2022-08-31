import sys
import types
import concat.stdlib.importlib
from typing import List, Callable, cast

# make this module callable
sys.modules[__name__].__class__ = concat.stdlib.importlib.Module


def cls(stack: List[object], stash: List[object]) -> None:
    """$inst -- $inst$.__class__"""
    stack.append(stack.pop().__class__)
