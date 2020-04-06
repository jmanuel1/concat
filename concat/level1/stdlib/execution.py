"""Execution flow combinators are based on those of RetroForth."""

from typing import List, Callable, cast
from concat.level0.stdlib.types import Quotation


def choose(stack: List[object], stash: List[object]) -> None:
    """flag $true_fun $false_fun -- `true_fun(stack, stash) if flag else false_fun(stack, stash)`"""
    false_fun, true_fun, flag = (stack.pop() for _ in range(3))
    (cast(Callable[[List[object], List[object]], None], true_fun) if flag else
        cast(Callable[[List[object], List[object]], None], false_fun))(stack, stash)


def if_then(stack: List[object], stash: List[object]) -> None:
    """flag $fun => flag $fun $() choose"""
    stack.append(Quotation())
    choose(stack, stash)


def if_not(stack: List[object], stash: List[object]) -> None:
    """flag $fun => flag $() $fun choose"""
    stack[-1:-1] = [Quotation()]
    choose(stack, stash)


def case(stack: List[object], stash: List[object]) -> None:
    """initial second $fun => `initial == second` $fun $initial choose

    Note that initial is popped off the stack in the true case."""
    fun, second, initial = (stack.pop() for _ in range(3))
    stack.append(initial == second)
    stack.append(fun)
    stack.append(lambda s, _: s.append(initial))
    choose(stack, stash)


# We use a non-recursive implementation so that generators can work with loop.
def loop(stack: List[object], stash: List[object]) -> None:
    """$fun => fun `while stack.pop(): ` fun """
    fun = cast(Callable[[List[object], List[object]], None], stack.pop())
    fun(stack, stash)
    while stack.pop():
        fun(stack, stash)
