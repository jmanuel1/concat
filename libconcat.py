import builtins
import sys
import functools
import operator


class Stack(list):

    def __init__(self, debug=False):
        self.debug = debug

    def _debug(self):
        if self.debug:
            builtins.print('DEBUG:', repr(self))

    def append(self, item):
        super().append(item)
        self._debug()

    def pop(self):
        value = super().pop()
        self._debug()
        return value

    def __setitem__(self, key, value):
        super().__setitem__(key, value)
        self._debug()


stack = Stack(debug=False)
stash = []


def unlist():
    stack[-1:] = stack[-1]


def tolist():
    n = stack.pop()
    stack[-n:] = [stack[-n:]]


def print():
    builtins.print(stack.pop(), end='')


def str():
    stack.append(builtins.str(stack.pop()))


# The following function is taken from Python's documentation
# (see functools.reduce), modified to use the stack.
# The required copyright notice:
# Copyright © 2001-2016 Python Software Foundation; All Rights Reserved
# The required license agreement: PSF_AGREEMENT.md
def reduce(): # iterable, initializer, function
    func, initializer, it = stack.pop(), stack.pop(), iter(stack.pop())

    if initializer is None:
        stack.append(next(it))
    else:
        stack.append(initializer)
    for element in it:
        stack.append(element)
        func()


def add():
    stack[-2:] = [operator.add(stack[-2], stack[-1])]


def map(): # iter func
    result = []
    for item in stack[-2]:
        stack.append(item)
        stack[-2]()
        result.append(stack.pop())
    stack[-2:] = [result]


def roll():
    n = stack.pop()
    stack[-(n+1):] = stack[-n:] + stack[-(n+1):-n]


def pop():
    stack.pop()


def over(): # a b
    stack.append(stack[-2])


def _r():
    stash.append(stack.pop())


def r_():
    stack.append(stash.pop())


def int():
    stack.append(builtins.int(stack.pop()))


def input():
    stack.append(builtins.input(stack.pop()))


def swap():
    stack[-2:] = [stack[-1], stack[-2]]


__all__ = dir()
