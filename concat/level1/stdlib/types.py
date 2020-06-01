
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


if __name__ == '__main__':
    print('42 example')
    quotation = Quotation([Quotation.yield_function])
    generator = quotation([42], [])
    assert generator is not None
    for item in generator:
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
