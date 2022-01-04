"""This module includes the Concat generator protocol.

Assume there is a function f that takes an object and pushes an object and another function onto the stack.

    def f(`s -- (... -- ...) `t): ...

Then f may represent an generator. `f` returns the first object yielded by the generator, along with a continuation representing the rest of the iteration. This continuation has the same type as f, or is the value None. If the continuation is None, then the generator is exhausted and the returned object is the return value of the generator.

In other words, if the type of an generator is denoted by GenType[`s, `t, `r], then GenType[`s, `t, `r] = (`s -- GenType[`s, `t, `r] `t) | (`s -- None `r).

Example:

    # A generator that returns the single value 42.
    def forty_two:
        drop None 42

Concat generators can be converted to fit Python's iterator protocol using the to_py_iter function defined in this module.

Prior art:

* https://developer.mozilla.org/en-US/docs/Web/JavaScript/Reference/Global_Objects/Generator
* https://developer.mozilla.org/en-US/docs/Web/JavaScript/Reference/Iteration_protocols
* https://softwareengineering.stackexchange.com/a/332383/153281
"""

from typing import Generator, List

_ConcatGenerator = Generator[object, object, None]


class Quotation(list):
    def __call__(self, stack: List[object], stash: List[object]) -> None:
        for element in self:
            element(stack, stash)


def to_py_iter(stack: List[object], stash: List[object]) -> None:
    quot = stack.pop()

    def generator() -> Generator[object, object, object]:
        stack_, stash_ = stack[:], stash[:]  # idk if this is necessary
        q = quot
        input = yield
        while True:
            stack_.append(input)
            q(stack_, stash_)
            q, value = stack_.pop(-2), stack_.pop()
            if not q:
                return value
            input = yield value

    g = generator()
    # advance g once so we can send in values immediately
    next(g)
    stack.append(g)
