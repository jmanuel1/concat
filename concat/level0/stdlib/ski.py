"""Combinators are based in the SKI Combinator Calculus and http://tunes.org/~iepos/joy.html"""


def i(stack, stash):
    """$A -- A"""
    A = stack.pop()
    A(stack, stash)
