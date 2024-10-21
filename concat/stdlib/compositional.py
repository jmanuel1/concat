"""Compositional combinators are based on those of RetroForth."""

from concat.stdlib.types import Quotation


def curry(stack, stash):
    """value $fun -- $(value fun)"""
    fun, value = (stack.pop() for _ in range(2))
    stack.append(Quotation([lambda s, _: s.append(value), fun]))
