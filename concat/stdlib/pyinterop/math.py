import sys
import math
import concat.stdlib.importlib
from typing import (
    List,
    cast,
    SupportsFloat,
)

# make this module callable
sys.modules[__name__].__class__ = concat.stdlib.importlib.Module


def sin(stack: List[object], stash: List[object]) -> None:
    """x -- math.sin(x)"""
    stack.append(math.sin(cast(SupportsFloat, stack.pop())))
