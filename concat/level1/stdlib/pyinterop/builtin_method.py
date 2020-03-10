import sys
import types
import concat.level0.stdlib.importlib
from typing import List, Callable, cast

# make this module callable
sys.modules[__name__].__class__ = concat.level0.stdlib.importlib.Module


def self(stack: List[object], stash: List[object]) -> None:
    """$method -- $method$.__self__"""
    stack.append(cast(types.MethodType, stack.pop()).__self__)
