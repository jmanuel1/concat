import builtins
import functools
import collections


class Stack(list):

    def __init__(self, name, debug=False):
        self.debug = debug
        self._name = name

    def _debug(self):
        if self.debug:
            builtins.print('DEBUG', self._name, ':',
                           repr([pythonify(obj) for obj in self]))

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


class ConcatFunction(collections.Callable):

    def __init__(self, func):
        self.func = func

    def __call__(self, stack, stash):
        func = self.func
        func(stack, stash)


class ConcatObject:

    def __init__(self, stack, stash):
        stack.append(self)

    def __getattribute__(self, attr):
        value = object.__getattribute__(self, attr)
        is_concat_function = callable(value) and attr not in {'_pythonify_',
                                                              '_concatify_'}
        if is_concat_function:
            # if value is callable and not a Python-Concat interface method
            return ConcatFunction(lambda stack, stash: value(stack, stash))
        return value

    def _pythonify_(self):
        return self


stack = Stack('stack', debug=False)
stash = Stack('stash', debug=False)


def _call(func, stack, stash):
    if isinstance(func, ConcatFunction):
        func(stack, stash)
    else:
        kwargs, args = stack.pop(), stack.pop()
        # These objects are about to enter Python, pythonify them
        args = pythonify(args)
        kwargs = {pythonify(key): pythonify(value)
                  for key, value in kwargs.items()}
        # Concatify the result
        stack.append(concatify(func(*args, **kwargs)))


def pythonify(obj):
    if isinstance(obj, ConcatObject):
        return obj._pythonify_()
    return obj


def concatify(obj):
    if type(obj) in concatify.table:
        concat_class = concatify.table[type(obj)]
        return concat_class._concatify_(obj)
    return obj


concatify.table = {}


@ConcatFunction
def _getitem(stack, stash):
    key, obj = stack.pop(), stack.pop()
    stack.append(key)
    _call(obj.__getitem__, stack, stash)


@ConcatFunction
def bytes(stack, stash):
    errors, encoding, string = [pythonify(stack.pop()) for _ in range(3)]
    if errors is None:
        stack.append(concatify(builtins.bytes(string, encoding)))
    else:
        stack.append(
            concatify(builtins.bytes(string, encoding, errors)))


@ConcatFunction
def unlist(stack, stash):
    stack[-1:] = pythonify(stack[-1])


@ConcatFunction
def tolist(stack, stash):
    n = stack.pop()
    stack[-n:] = [concatify(stack[-n:])]


@ConcatFunction
def print(stack, stash):
    builtins.print(pythonify(stack.pop()), end='')


@ConcatFunction
def str(stack, stash):
    stack.append(builtins.str(stack.pop()))


@ConcatFunction
def reduce(stack, stash):  # iterable, initializer, function
    func, initializer, it = stack.pop(), stack.pop(), stack.pop()

    def reduce_func(a, b):
        nonlocal stack
        stack += [a, b]
        func(stack, stash)
        return stack.pop()
    stack.append(
        concatify(functools.reduce(reduce_func, pythonify(it), initializer)))


@ConcatFunction
def add(stack, stash):
    b, a = stack.pop(), stack.pop()
    stack.append(b)
    a.__add__(stack, stash)


@ConcatFunction
def map(stack, stash):  # iter func
    result = []
    func, it = stack.pop(), stack.pop()
    for item in pythonify(it):
        stack.append(concatify(item))
        func(stack, stash)
        result.append(stack.pop())
    stack.append(concatify(result))


@ConcatFunction
def ident(stack, stash): pass


@ConcatFunction
def dup(stack, stash):
    stack.append(stack[-1])


@ConcatFunction
def nip(stack, stash):
    stack[-2:-1] = []


@ConcatFunction
def nip2(stack, stash):
    stack[-3:-1] = []


@ConcatFunction
def roll(stack, stash):
    n = stack.pop()
    # NOTE: this is meant to roll n+1 elements
    stack[-(n+1):] = stack[-n:] + stack[-(n+1):-n]


@ConcatFunction
def pop(stack, stash):
    stack.pop()


@ConcatFunction
def over(stack, stash):  # a b
    stack.append(stack[-2])


@ConcatFunction
def _r(stack, stash):
    stash.append(stack.pop())


@ConcatFunction
def r_(stack, stash):
    stack.append(stash.pop())


@ConcatFunction
def int(stack, stash):
    stack.append(concatify(builtins.int(pythonify(stack.pop()))))


@ConcatFunction
def input(stack, stash):
    stack.append(concatify(builtins.input(pythonify(stack.pop()))))


@ConcatFunction
def swap(stack, stash):
    stack[-2:] = [stack[-1], stack[-2]]


@ConcatFunction
def sorted(stack, stash):
    reverse, key, iterable = [pythonify(stack.pop()) for _ in range(3)]

    def new_key(el):
        stack.append(el)
        key(stack, stash)
        return stack.pop()
    stack.append(builtins.sorted(iterable, key=new_key, reverse=reverse))


@ConcatFunction
def dup2(stack, stash):
    stack += stack[-2:]


__all__ = dir()
