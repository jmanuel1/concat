"""Type stubs for the parsy module."""


from typing import (TypeVar, List, Union, Generic,
                    Callable, Generator, Optional, Protocol, overload)


T = TypeVar('T')
U = TypeVar('U')
V = TypeVar('V')
W = TypeVar('W')


class _SupportsPlus(Protocol):

    def __add__(self, other: '_SupportsPlus') -> '_SupportsPlus':
        ...


class Result:
    status: bool
    furthest: int
    expected: str

    @staticmethod
    def failure(furthest: int, expected: str) -> 'Result':
        ...


class Parser(Generic[T, U]):

    def __init__(
        self,
        func: Callable[[Union[str, List[T]], int], Result]
    ) -> None:
        ...

    def parse(self, string_or_list: Union[str, List[T]]) -> U:
        ...

    def many(self) -> 'Parser[T, List[U]]':
        ...

    def optional(self) -> 'Parser[T, Optional[U]]':
        ...

    def map(self, fn: Callable[[U], V]) -> 'Parser[T, V]':
        ...

    def sep_by(self,
               sep: 'Parser[T, V]', min=0, max=float('inf')
               ) -> 'Parser[T, List[U]]':
        ...

    def times(self, min: int, max: int = -1) -> 'Parser[T, List[U]]':
        ...

    def result(self, res: V) -> 'Parser[T, V]':
        ...

    def at_least(self, n: int) -> '_ParserOutputtingList[T, U]':
        ...

    def __lshift__(self, other: 'Parser[T, V]') -> 'Parser[T, U]':
        ...

    def __or__(self, other: 'Parser[T, V]') -> 'Parser[T, Union[U, V]]':
        ...

    def __rshift__(self, other: 'Parser[T, V]') -> 'Parser[T, V]':
        ...

    def __add__(self,
                other: 'Parser[T, _SupportsPlus]'
                ) -> 'Parser[T, _SupportsPlus]':
        ...

    def __call__(self, stream: Union[str, List[T]], index: int) -> Result:
        ...


class _ParserOutputtingList(Parser[T, List[U]]):

    def combine(self, fn: Callable[..., V]) -> Parser[T, V]:
        ...


class ParseError(Exception):
    ...


def test_item(func: Callable[[T], bool], description: str) -> Parser[T, T]:
    ...


ParserGeneratingFunction = Callable[[], Generator[Parser[T, U], U, V]]


@overload
def generate(
    desc: str
) -> Callable[[ParserGeneratingFunction[T, U, V]], Parser[T, V]]:
    ...


@overload
def generate(generator: ParserGeneratingFunction[T, U, V]) -> Parser[T, V]:
    ...


def alt(*parsers: Parser[T, U]) -> Parser[T, U]:
    ...


def seq(*parsers: Parser[T, U]) -> _ParserOutputtingList[T, U]:
    ...

# there is another seq overload for Python 3.6+, but we support 3.5+


def success(val: T) -> Parser[U, T]:
    ...


def peek(parser: Parser[T, U]) -> Parser[T, U]:
    ...


any_char: Parser
