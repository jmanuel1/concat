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

from typing import List, NoReturn, Generator, Optional, Callable, cast
import concat.level0.stdlib.types

_ConcatGenerator = Generator[object, object, None]


class _YieldException(Exception):
    def __init__(self, continuation: Callable[[List[object], List[object]], None]) -> None:
        self.continuation = continuation


class Quotation(concat.level0.stdlib.types.Quotation):

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self._is_generator_function = False

    def __call__(
        self, stack: List[object], stash: List[object]
    ) -> Optional[_ConcatGenerator]:
        if self._is_generator_function:
            # Copy the stack and stash since they could change between each
            # resumption.
            generator = self._call_as_generator(stack[:], stash[:])
            # push generator onto stack as a return value
            stack.append(generator)
            return generator
        return super().__call__(stack, stash)

    @staticmethod
    def yield_function(stack: List[object], __: List[object]) -> NoReturn:
        raise _YieldException(
            cast(Callable[[List[object], List[object]], None], stack.pop()))

    def _call_as_generator(
        self, stack: List[object], stash: List[object]
    ) -> _ConcatGenerator:
        """Execute the quotation like a Python generator.

        Note that control is returned to the next element of a quotation after
        a yield. That means that in the code `(42 yield unreachable) reached`,
        the word `unreachable` is never executed.
        """
        # done = False
        # while not done:
        #     super().__call__(stack, stash)
        #     next_func = stack.pop()
        #     value = stack.pop()
        #     yield value
        #     if next_func is None:
        #         done = True
        #     else:
        raise NotImplementedError

    def make_generator_function(self, stack: List[object], stash: List[object]) -> 'Quotation':
        copy = Quotation(self)
        try:
            yield_index = copy.index(Quotation.yield_function)
        except ValueError:
            pass
        else:
            continuation = Quotation(copy[yield_index +
                                          1:]).make_generator_function(stack, stash)
            copy[yield_index + 1:] = []
            copy[-1:-1] = [lambda s, t: s.append(continuation)]
        copy._is_generator_function = True
        stack.append(copy)
        return copy


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


if __name__ == '__main__':
    from concat.level1.stdlib.shuffle_words import drop

    print('42 example')
    quotation = Quotation([drop, lambda s, _: s.append(Quotation([drop, lambda s, _: s.append(None), lambda s, _: s.append(None)])), lambda s, _: s.append(42)])
    stack = [quotation]
    to_py_iter(stack, [])
    for item in stack.pop():
        print(item)
#
#     # TODO: Given the way generators currently work, I don't think the
#     # following example can be written without falling back onto some of
#     # Python's control structures.
#
#     print('hailstone sequence of 42 example')
#     # Imports for example
#     from concat.level1.stdlib.shuffle_words import dup, drop
#     from concat.level1.stdlib.execution import choose, loop
#
#     quotation_2 = Quotation([
#         lambda s, t: s.append(Quotation([
#             lambda s, t: s.append(s[-1] == 1),
#             lambda s, t: s.append(Quotation([Quotation.yield_function, drop,
#                                              lambda s, t: s.append(False)])),
#             lambda s, t: s.append(Quotation([
#                 dup, Quotation.yield_function, drop,
#                 lambda s, t: s.append(s.pop() % 2 == 0),
#                 lambda s, t: s.append(lambda s, t: s.append(s.pop()//2)),
#                 lambda s, t: s.append(lambda s, t: s.append(3*s.pop() + 1)),
#                 choose,
#                 lambda s, t: s.append(True)
#             ])),
#             choose
#         ])),
#         loop
#     ]).make_generator_function([], [])
#     generator_2 = quotation_2([42], [])
#     assert generator_2 is not None
#     for number in generator_2:
#         print(number)
