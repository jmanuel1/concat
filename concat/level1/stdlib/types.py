from typing import List, NoReturn, Generator, Optional
import concat.level0.stdlib.types


_ConcatGenerator = Generator[object, object, None]


class _YieldException(Exception):
    pass


class Quotation(concat.level0.stdlib.types.Quotation):

    def __call__(
        self, stack: List[object], stash: List[object]
    ) -> Optional[_ConcatGenerator]:
        if Quotation.yield_function in self:
            # Copy the stack and stash since they could change between each
            # resumption.
            generator = self._call_as_generator(stack[:], stash[:])
            # push generator onto stack as a return value
            stack.append(generator)
            return generator
        return super().__call__(stack, stash)

    @staticmethod
    def yield_function(_: List[object], __: List[object]) -> NoReturn:
        raise _YieldException

    def _call_as_generator(
        self, stack: List[object], stash: List[object]
    ) -> _ConcatGenerator:
        """Execute the quotation like a Python generator.

        Note that control is returned to the next element of a quotation after
        a yield. That means that in the code `(42 yield unreachable) reached`,
        the word `unreachable` is never executed.
        """
        for element in self:
            try:
                element(stack, stash)
            except _YieldException:
                stack.append((yield stack.pop()))
            # TODO: Implement yield_from


if __name__ == '__main__':
    print('42 example')
    quotation = Quotation([Quotation.yield_function])
    generator = quotation([42], [])
    assert generator is not None
    for item in generator:
        print(item)

    # TODO: Given the way generators currently work, I don't think the
    # following example can be written without falling back onto some of
    # Python's control structures.

    # print('hailstone sequence of 42 example')
    # # Imports for example
    # from concat.level1.stdlib.shuffle_words import dup, drop
    # from concat.level1.stdlib.execution import choose, loop
    #
    # def quotation_2(s, _):
    #     return Quotation([
    #         lambda s, _: s.append(Quotation([
    #             lambda s, _: print('stack is', s, 'at start of quotation_2'),
    #             lambda s, _: print(s[-1]),
    #             dup,
    #             Quotation.yield_function, drop,
    #             lambda s, _: s.append(drop),
    #             lambda s, _: s.append(Quotation([
    #                 lambda s, _: s.append(s[-1] % 2 == 0),
    #                 lambda s, _: s.append(Quotation([
    #                     lambda s, _: s.append(s.pop()//2)
    #                 ])),
    #                 lambda s, _: s.append(Quotation([
    #                     lambda s, _: s.append(3*s.pop() + 1)
    #                 ])),
    #                 lambda s, _: print('stack is', s),
    #                 choose,
    #             ])),
    #             lambda s, _: print('stack is', s),
    #             lambda s, _: s.append(s[-1] != 1),
    #         ])),
    #         loop
    #     ])(s, _)
    # generator_2 = quotation_2([42], [])
    # assert generator_2 is not None
    # for number in generator_2:
    #     print(number)
