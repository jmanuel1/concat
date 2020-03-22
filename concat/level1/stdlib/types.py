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
            generator = self._call_as_generator(stack, stash)
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


if __name__ == '__main__':
    quotation = Quotation([Quotation.yield_function])
    generator = quotation([42], [])
    assert generator is not None
    for item in generator:
        print(item)
