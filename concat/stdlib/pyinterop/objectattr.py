import sys
import types
import concat.stdlib.importlib
from typing import Callable, List, Union, cast
from typing_extensions import Protocol


class _SupportsSelf(Protocol):
    __self__: object


class _SupportsName(Protocol):
    __name__: str


def self(stack: List[object], stash: List[object]) -> None:
    """x -- x$.__self__

    x could be a method or a built-in function, for example."""

    stack.append(cast(_SupportsSelf, stack.pop()).__self__)


def doc(stack: List[object], stash: List[object]) -> None:
    """x -- x$.__doc__"""
    stack.append(stack.pop().__doc__)


def name(stack: List[object], stash: List[object]) -> None:
    """x -- x$.__name__

    x could be callable, module, or type, for example."""
    stack.append(cast(_SupportsName, stack.pop()).__name__)


def module(stack: List[object], stash: List[object]) -> None:
    """x -- x$.__module__"""
    stack.append(stack.pop().__module__)


def annotations(stack: List[object], stash: List[object]) -> None:
    """$x -- $x$.__annotations__"""
    stack.append(stack.pop().__annotations__)


def dict(stack: List[object], stash: List[object]) -> None:
    """$x -- $x$.__dict__"""
    stack.append(stack.pop().__dict__)
