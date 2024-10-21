"""Shuffle words are based on those of Factor and RetroForth.

We do not borrow Factor's deprecated 'complex' shuffle words."""

from typing import List


def drop(stack: List[object], stash: List[object]) -> None:
    """x --"""
    stack.pop()


def drop_2(stack: List[object], stash: List[object]) -> None:
    """x y --"""
    stack.pop()
    stack.pop()


def drop_3(stack: List[object], stash: List[object]) -> None:
    """x y z --"""
    stack.pop()
    stack.pop()
    stack.pop()


def nip(stack: List[object], stash: List[object]) -> None:
    """x y -- y"""
    stack.pop(-2)


def nip_2(stack: List[object], stash: List[object]) -> None:
    """x y z -- z"""
    stack.pop(-2)
    stack.pop(-2)


def dup(stack: List[object], stash: List[object]) -> None:
    """x -- x x"""
    stack.append(stack[-1])


def dup_2(stack: List[object], stash: List[object]) -> None:
    """x y -- x y x y"""
    stack.append(stack[-2])
    stack.append(stack[-2])


def swap(stack: List[object], stash: List[object]) -> None:
    """x y -- y x"""
    stack[-2], stack[-1] = stack[-1], stack[-2]


def dup_3(stack: List[object], stash: List[object]) -> None:
    """x y z -- x y z x y z"""
    stack += [stack[-3], stack[-2], stack[-1]]


def over(stack: List[object], stash: List[object]) -> None:
    """x y -- x y x"""
    stack += [stack[-2]]


def over_2(stack: List[object], stash: List[object]) -> None:
    """x y z -- x y z x y"""
    stack += [stack[-3], stack[-2]]


def pick(stack: List[object], stash: List[object]) -> None:
    """x y z -- x y z x"""
    stack += [stack[-3]]
