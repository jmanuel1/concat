import sys
import types
import concat.stdlib.importlib
from typing import List, Callable, cast

# make this module callable
sys.modules[__name__].__class__ = concat.stdlib.importlib.Module


def file(stack: List[object], stash: List[object]) -> None:
    """$mod -- $mod$.__file__"""
    stack.append(cast(types.ModuleType, stack.pop()).__file__)
