"""Combinators are based on the SKI Combinator Calculus and http://tunes.org/~iepos/joy.html"""


from concat.stdlib.types import Quotation


def s(stack, stash):
    """$C $B $A -- $($C B) $C A"""
    A, B, C = (stack.pop() for _ in range(3))
    stack.append(Quotation([C, B]))
    stack.append(C)
    A(stack, stash)


def k(stack, stash):
    """$B $A -- A"""
    A, B = stack.pop(), stack.pop()
    A(stack, stash)


def i(stack, stash):
    """$A -- A"""
    A = stack.pop()
    A(stack, stash)
