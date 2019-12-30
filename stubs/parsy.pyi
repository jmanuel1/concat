"""Type stubs for the parsy module."""


from typing import TypeVar, List, Union, Generic, Callable, Generator, Optional


T = TypeVar('T')
U = TypeVar('U')
V = TypeVar('V')


class Parser(Generic[T, U]):

    def parse(self, string_or_list: Union[str, List[T]]) -> U:
        ...

    def many(self) -> 'Parser[T, List[U]]':
        ...

    def optional(self) -> 'Parser[T, Optional[U]]':
        ...

    def map(self, fn: Callable[[U], V]) -> 'Parser[T, V]':
        ...

    def __lshift__(self, other: 'Parser[T, V]') -> 'Parser[T, U]':
        ...

    def __or__(self, other: 'Parser[T, V]') -> 'Parser[T, Union[U, V]]':
        ...

    def __rshift__(self, other: 'Parser[T, V]') -> 'Parser[T, V]':
        ...


def test_item(func: Callable[[T], bool], description: str) -> Parser[T, T]:
    ...


def generate(desc: str) -> Callable[[Callable[[], Generator[Parser[T, U], U, V]]], Parser[T, V]]:
    ...


def alt(*parsers: Parser[T, U]) -> Parser[T, U]:
    ...
