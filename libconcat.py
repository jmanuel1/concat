import builtins
import operator
import importlib
import inspect
# import traceback


class Stack(list):

    def __init__(self, name, debug=False):
        self.debug = debug
        self._name = name

    def _debug(self):
        if self.debug:
            builtins.print('DEBUG', self._name, ':', repr(self))

    def append(self, item):
        super().append(item)
        # if item is None:
        #     builtins.print('ITEM PUSHED:', item)
        #     builtins.print(''.join(traceback.format_stack()))
        self._debug()

    def pop(self):
        value = super().pop()
        self._debug()
        return value

    def __setitem__(self, key, value):
        super().__setitem__(key, value)
        self._debug()


class ConvertedModule:
    def __init__(self, m):
        self.m = m

    def __getattr__(self, key):
        attr = getattr(self.m, key)
        try:
            nargs = len(inspect.signature(attr).parameters)
        except TypeError:
            # not a callable
            return attr
        except ValueError:
            # no signature
            module = self._get_std_module_override(self.m.__name__)

            def method():
                getattr(module, key)(stack)
            return method

        def method():
            args = stack[len(stack) - nargs:]
            stack[len(stack) - nargs:] = [attr(*args)]
        return method

    def _get_std_module_override(self, name):
        return importlib.import_module('stdoverrides.{}_'.format(name))


class ConvertedObject:
    def __init__(self, obj):
        self.obj = obj

    def __getattr__(self, key):
        if isinstance(self.obj, ConvertedModule):
            return getattr(self.obj, key)

        attr = getattr(self.obj, key)
        try:
            nargs = len(inspect.signature(attr).parameters)
        except TypeError:
            # not a callable
            return attr
        except ValueError:
            # no signature
            # builtins.print('OVERRIDE')
            typ = self._get_builtin_type_override(type(self.obj).__name__)

            def method():
                getattr(typ(self.obj), key)(stack)
            # builtins.print('END OVERRIDE')
            return method

        def method():
            args = stack[len(stack) - nargs:]
            stack[len(stack) - nargs:] = [attr(*args)]
        return method

    def _get_builtin_type_override(self, name):
        import stdoverrides.builtintypes as bto
        return getattr(bto, name)

stack = Stack('stack', debug=False)
stash = Stack('stash', debug=False)


def bytes():
    errors, encoding, string = [stack.pop() for _ in range(3)]
    if errors is None:
        stack.append(builtins.bytes(string, encoding))
    else:
        stack.append(builtins.bytes(string, encoding, errors))


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
# TODO: use python's reduce using technique for sorted implementation
def reduce():  # iterable, initializer, function
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


def map():  # iter func
    result = []
    func, it = stack.pop(), stack.pop()
    for item in it:
        stack.append(item)
        func()
        result.append(stack.pop())
    stack.append(result)


def dup():
    stack.append(stack[-1])


def nip():
    stack[-2:-1] = []


def nip2():
    stack[-3:-1] = []


def roll():
    n = stack.pop()
    stack[-(n):] = stack[-n+1:] + stack[-(n):-n+1]


def pop():
    stack.pop()


def over():  # a b
    stack.append(stack[-2])


def import_and_convert(module):
    m = importlib.import_module(module)
    return ConvertedModule(m)


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


def sorted():
    reverse, key, iterable = stack.pop(), stack.pop(), stack.pop()

    def new_key(el):
        stack.append(el)
        key()
        return stack.pop()
    stack.append(builtins.sorted(iterable, key=new_key, reverse=reverse))


def dup2():
    global stack
    stack += stack[-2:]

__all__ = dir()
