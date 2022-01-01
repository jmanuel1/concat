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


if __name__ == '__main__':
    from concat.stdlib.shuffle_words import drop

    print('42 example')
    quotation = Quotation(
        [
            drop,
            lambda s, _: s.append(
                Quotation(
                    [
                        drop,
                        lambda s, _: s.append(None),
                        lambda s, _: s.append(None),
                    ]
                )
            ),
            lambda s, _: s.append(42),
        ]
    )
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
#     from concat.stdlib.shuffle_words import dup, drop
#     from concat.stdlib.execution import choose, loop
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
