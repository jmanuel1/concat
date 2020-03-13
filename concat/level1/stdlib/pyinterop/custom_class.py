import sys
import concat.level0.stdlib.importlib
from typing import List, cast

# make this module callable
sys.modules[__name__].__class__ = concat.level0.stdlib.importlib.Module


def doc(stack: List[object], stash: List[object]) -> None:
    """$cls -- $cls$.__doc__"""
    stack.append(stack.pop().__doc__)


def name(stack: List[object], stash: List[object]) -> None:
    """$cls -- $cls$.__name__"""
    stack.append(cast(type, stack.pop()).__name__)


def annotations(stack: List[object], stash: List[object]) -> None:
    """$cls -- $cls$.__annotations__"""
    stack.append(cast(type, stack.pop()).__annotations__)


def bases(stack: List[object], stash: List[object]) -> None:
    """$cls -- $cls$.__bases__"""
    stack.append(cast(type, stack.pop()).__bases__)


def dict(stack: List[object], stash: List[object]) -> None:
    """$cls -- $cls$.__dict__"""
    stack.append(cast(type, stack.pop()).__dict__)


def module(stack: List[object], stash: List[object]) -> None:
    """$cls -- $cls$.__dict__"""
    stack.append(cast(type, stack.pop()).__module__)
