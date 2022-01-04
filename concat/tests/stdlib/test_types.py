from concat.execute import LoggableStack
from concat.stdlib.compositional import curry
from concat.stdlib.execution import choose
from concat.stdlib.shuffle_words import drop, swap
import concat.stdlib.types
from concat.stdlib.types import Quotation
import unittest
from typing import Iterator, Generator, List, Callable, cast


class TestQuotations(unittest.TestCase):
    def __push(
        self, value: object
    ) -> Callable[[List[object], List[object]], None]:
        return lambda stack, _: stack.append(value)

    def test_quoted_list_is_equal_to_list(self) -> None:
        lst = [1, 2, 3]
        quote = concat.stdlib.types.Quotation(lst)
        self.assertEqual(quote, lst, msg='Quotation([1, 2, 3]) != [1, 2, 3]')

    def test_quotation_is_callable(self) -> None:
        quote = concat.stdlib.types.Quotation([self.__push('c')])
        stack: List[object] = []
        quote(stack, [])
        self.assertEqual(
            ['c'], stack, msg='quotations do not behave correctly when called'
        )


class TestGeneratorProtocol(unittest.TestCase):
    def test_singleton(self) -> None:
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
        stack: List[object] = [quotation]
        concat.stdlib.types.to_py_iter(stack, [])
        actual = list(cast(Iterator[int], stack.pop()))
        self.assertEqual(actual, [42])

    def test_hailstone_sequence(self) -> None:
        def fun(stack, stash) -> None:
            drop(stack, stash)
            n = stack.pop()
            stack.append(n == 1)
            stack.append(
                Quotation(
                    [
                        lambda s, t: s.append(
                            Quotation([lambda s, t: s.extend([None, None])])
                        ),
                        lambda s, t: s.append(n),
                    ]
                )
            )
            stack.append(
                Quotation(
                    [
                        lambda s, t: s.append(n),
                        lambda s, t: s.append(fun2),
                        curry,
                        lambda s, t: s.append(n),
                    ]
                )
            )
            choose(stack, stash)

        def fun2(stack, stash) -> None:
            n = stack.pop()
            drop(stack, stash)
            stack.append(n % 2 == 0)
            stack.append(lambda s, t: s.append(n // 2))
            stack.append(lambda s, t: s.append(3 * n + 1))
            choose(stack, stash)
            stack.append(None)
            fun(stack, stash)

        stack = LoggableStack('stack', should_log=False)
        stack.extend([42, fun])
        concat.stdlib.types.to_py_iter(stack, [])
        actual = list(cast(Iterator[int], stack.pop()))
        self.assertEqual(actual, [42, 21, 64, 32, 16, 8, 4, 2, 1])

    def test_return(self) -> None:
        quotation = Quotation(
            [
                drop,
                lambda s, _: s.append(
                    Quotation(
                        [
                            drop,
                            lambda s, _: s.append(None),
                            lambda s, _: s.append('a return value'),
                        ]
                    )
                ),
                lambda s, _: s.append(42),
            ]
        )
        stack = LoggableStack('stack', should_log=False)
        stack.extend([quotation])
        concat.stdlib.types.to_py_iter(stack, [])
        generator = cast(Iterator[object], stack.pop())
        for _ in range(10):
            try:
                next(generator)
            except StopIteration as e:
                self.assertEqual(e.value, 'a return value')
                return
        self.fail('generator did not stop')

    def test_send(self) -> None:
        quotation = Quotation([lambda s, _: s.append(None), swap])
        stack = LoggableStack('stack', should_log=False)
        stack.extend([quotation])
        concat.stdlib.types.to_py_iter(stack, [])
        generator = cast(Generator[int, int, None], stack.pop())
        for _ in range(1):
            try:
                generator.send(42)
            except StopIteration as e:
                self.assertEqual(e.value, 42)
                return
        self.fail('generator did not stop')
