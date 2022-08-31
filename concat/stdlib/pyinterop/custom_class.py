import sys
import concat.stdlib.importlib
from typing import List, cast

# make this module callable
sys.modules[__name__].__class__ = concat.stdlib.importlib.Module


def bases(stack: List[object], stash: List[object]) -> None:
    """$cls -- $cls$.__bases__"""
    stack.append(cast(type, stack.pop()).__bases__)
