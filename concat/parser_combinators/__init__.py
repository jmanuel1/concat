"""Parser combinators.

Error handling is based on the blog post "Parser Combinators and Error
Reporting" for better error messages.
"""

import itertools
from typing import (
    Any,
    Callable,
    Generator,
    Generic,
    Iterable,
    Iterator,
    Sequence,
    Tuple,
    TypeVar,
    Optional,
    Union,
    List,
    cast,
    overload,
)
from typing_extensions import Protocol


class _SupportsPlus(Protocol):
    def __add__(self, other: '_SupportsPlus') -> '_SupportsPlus': ...


T = TypeVar('T')
_T_co = TypeVar('_T_co', covariant=True)
_T_contra = TypeVar('_T_contra', contravariant=True)
U = TypeVar('U')
_U_co = TypeVar('_U_co', covariant=True)
_U_supports_plus = TypeVar('_U_supports_plus', bound=_SupportsPlus)
_V = TypeVar('_V')
V = TypeVar('V')


def _maybe_inf_range(minimum: int, maximum: float) -> Iterable[int]:
    if maximum == float('inf'):
        return itertools.count(minimum)
    return range(minimum, int(maximum))


class FailureTree:
    """Failure messages and positions from parsing.

    Failures can be nested."""

    def __init__(
        self, expected: str, furthest_index: int, children: List['FailureTree']
    ) -> None:
        self.expected = expected
        self.furthest_index = furthest_index
        self.children = children

    def __repr__(self) -> str:
        return f'{type(self).__qualname__}({self.expected!r}, {self.furthest_index!r}, {self.children!r})'

    def __eq__(self, other: object) -> bool:
        if isinstance(other, FailureTree):
            return (self.expected, self.furthest_index, self.children) == (
                other.expected,
                other.furthest_index,
                other.children,
            )
        return NotImplemented

    def __hash__(self) -> int:
        return hash((self.expected, self.furthest_index, tuple(self.children)))


def furthest_failure(failures: Iterable[FailureTree]) -> Optional[FailureTree]:
    furthest_index = -1
    result = None
    for failure in failures:
        if failure.furthest_index > furthest_index:
            furthest_index = failure.furthest_index
            result = failure
    return result


class Result(Generic[_T_co]):
    """Class representing the output of a parser and the parsing state."""

    def __init__(
        self,
        output: _T_co,
        current_index: int,
        is_success: bool,
        failures: Optional[FailureTree] = None,
        is_committed: bool = False,
    ) -> None:
        self.output = output
        self.current_index = current_index
        if not is_success and failures is None:
            raise ValueError(
                f'{type(self).__qualname__} representing failure should have a failure tree'
            )
        self.is_success = is_success
        self.failures = failures
        self.is_committed = is_committed

    def __repr__(self) -> str:
        return f'{type(self).__qualname__}({self.output!r}, {self.current_index!r}, {self.is_success!r}, {self.failures!r}, is_committed={self.is_committed!r})'

    def __eq__(self, other: object) -> bool:
        if isinstance(other, Result):
            return (
                self.output,
                self.current_index,
                self.is_success,
                self.failures,
                self.is_committed,
            ) == (
                other.output,
                other.current_index,
                other.is_success,
                other.failures,
                other.is_committed,
            )
        return NotImplemented

    def __hash__(self) -> int:
        return hash(
            (
                self.output,
                self.current_index,
                self.is_success,
                self.failures,
                self.is_committed,
            )
        )


class Parser(Generic[_T_contra, _U_co]):
    """A parser in the functional style."""

    def __init__(
        self, f: Callable[[Sequence[_T_contra], int], Result[_U_co]]
    ) -> None:
        self._f = f

    def __or__(
        self, other: 'Parser[_T_contra, _V]'
    ) -> 'Parser[_T_contra, Union[_U_co, _V]]':
        @Parser
        def new_parser(
            stream: Sequence[_T_contra], index: int
        ) -> Result[Union[_U_co, _V]]:
            left_result = self(stream, index)
            if (
                left_result.is_success
                or left_result.is_committed
                and left_result.current_index > index
            ):
                return left_result
            right_result = other(stream, index)
            new_failure: Optional[FailureTree]
            if right_result.is_success:
                if left_result.current_index > right_result.current_index:
                    if right_result.failures is not None:
                        assert left_result.failures is not None
                        new_failure = FailureTree(
                            f'{left_result.failures.expected} or {right_result.failures.expected}',
                            left_result.failures.furthest_index,
                            left_result.failures.children
                            + right_result.failures.children,
                        )
                    else:
                        new_failure = left_result.failures
                    return Result(
                        right_result.output,
                        right_result.current_index,
                        True,
                        new_failure,
                    )
                return right_result
            if (
                right_result.is_committed
                and right_result.current_index > index
            ):
                return right_result
            assert left_result.failures is not None
            assert right_result.failures is not None
            new_failure = furthest_failure(
                [left_result.failures, right_result.failures]
            )
            output: Union[_U_co, _V] = (
                left_result.output
                if new_failure is left_result.failures
                else right_result.output
            )
            current_index = (
                left_result.current_index
                if new_failure is left_result.failures
                else right_result.current_index
            )
            return Result(output, current_index, False, new_failure)

        return new_parser

    def __add__(
        self: 'Parser[T, _U_supports_plus]',
        other: 'Parser[T, _U_supports_plus]',
    ) -> 'Parser[T, _U_supports_plus]':
        @generate
        def new_parser() -> Generator:
            first = yield self
            second = yield other
            return first + second

        return new_parser

    # This is based upon parsy's desc combinator: see license.
    def desc(self, description: str) -> 'Parser[_T_contra, _U_co]':
        @Parser
        def new_parser(
            stream: Sequence[_T_contra], index: int
        ) -> Result[_U_co]:
            result = self(stream, index)
            if not result.is_success and result.failures is not None:
                if result.current_index == index:
                    new_failure = FailureTree(
                        description, result.failures.furthest_index, []
                    )
                    return Result(result.output, index, False, new_failure)
                new_failure = FailureTree(
                    description,
                    result.failures.furthest_index,
                    [result.failures],
                )
                return Result(
                    result.output, result.current_index, False, new_failure
                )
            return result

        return new_parser

    def map(
        self, fn: Callable[[_U_co], V]
    ) -> 'Parser[_T_contra, Union[_U_co, V]]':
        @Parser
        def new_parser(
            stream: Sequence[_T_contra], index: int
        ) -> Result[Union[_U_co, V]]:
            result = self(stream, index)
            if result.is_success:
                return Result(
                    fn(result.output),
                    result.current_index,
                    True,
                    result.failures,
                )
            return result

        return new_parser

    def bind(
        self, f: Callable[[_U_co], 'Parser[_T_contra, V]']
    ) -> 'Parser[_T_contra, V]':
        @generate
        def new_parser() -> Generator:
            a = yield self
            return (yield f(a))

        return new_parser

    def __rshift__(
        self, other: 'Parser[_T_contra, V]'
    ) -> 'Parser[_T_contra, Union[tuple, V]]':
        return seq(self, other).map(lambda tup: tup[1])

    def __lshift__(
        self, other: 'Parser[_T_contra, V]'
    ) -> 'Parser[_T_contra, Union[tuple, _U_co]]':
        return seq(self, other).map(lambda tup: tup[0])

    def times(
        self, min: int, max: float = float('inf')
    ) -> 'Parser[_T_contra, List[_U_co]]':
        @generate
        def new_parser() -> Generator:
            output = []
            for _ in range(min):
                result = yield self
                output.append(result)
            for _ in _maybe_inf_range(min, max):
                result = yield self.map(lambda val: (val,)).optional()  # type: ignore
                if result is not None:
                    output.append(result[0])
                    continue
                break
            return output

        return new_parser

    def many(self) -> 'Parser[_T_contra, List[_U_co]]':
        return self.times(min=0)

    def at_least(self, n: int) -> 'Parser[_T_contra, List[_U_co]]':
        return self.times(min=n)

    def result(self, res: V) -> 'Parser[_T_contra, V]':
        @generate
        def new_parser() -> Generator:
            yield self
            return res

        return new_parser

    def sep_by(
        self, sep: 'Parser[_T_contra, V]', min=0, max=float('inf')
    ) -> 'Parser[_T_contra, List[_U_co]]':
        @generate
        def new_parser() -> Generator:
            output = []
            for i in range(min):
                output.append((yield self))
                if i != min - 1:
                    yield sep
            if max <= min:
                return output
            for i in _maybe_inf_range(min, max):
                if i == 0:
                    maybe_item = yield self.map(lambda val: (val,)).optional()  # type: ignore
                else:
                    maybe_item = yield (
                        sep >> self.map(lambda val: (val,))  # type: ignore
                    ).optional()
                if maybe_item is None:
                    break
                output.append(maybe_item[0])
            return output

        return new_parser

    def optional(self) -> 'Parser[_T_contra, Optional[_U_co]]':
        return self | success(None)

    # See
    # https://elixirforum.com/t/parser-combinators-how-to-know-when-many-should-return-an-error/46048/12
    # on the problem this solves.
    def commit(self) -> 'Parser[_T_contra, _U_co]':
        """Do not try alteratives adjacent to this parser if it consumes input before failure.

        This is useful with combinators like many(): parser.many() succeeds
        even if `parser` fails in a way that you know is an error and should be
        reported for a better error message."""

        @Parser
        def new_parser(
            stream: Sequence[_T_contra], index: int
        ) -> Result[_U_co]:
            result = self(stream, index)
            return Result(
                result.output,
                result.current_index,
                result.is_success,
                result.failures,
                is_committed=True,
            )

        return new_parser

    def concat(
        self: 'Parser[_T_contra, Iterable[str]]',
    ) -> 'Parser[_T_contra, Iterable[str]]':
        return self.map(''.join)

    def __call__(
        self, stream: Sequence[_T_contra], index: int
    ) -> Result[_U_co]:
        return self._f(stream, index)

    def parse(self, seq: Sequence[_T_contra]) -> _U_co:
        result = self(seq, 0)
        if result.current_index < len(seq):
            if result.failures is None:
                failure_children = []
            else:
                failure_children = [result.failures]
            result = Result(
                result.output,
                result.current_index,
                False,
                FailureTree(
                    'end of input',
                    result.current_index,
                    failure_children,
                ),
            )
        if result.is_success:
            return result.output
        raise ParseError(result)


class ParseError(Exception):
    """Exception raised for unrecoverable parser errors."""


def success(val: T) -> Parser[Any, T]:
    return seq().result(val)


def seq(*parsers: 'Parser[T, Any]') -> 'Parser[T, tuple]':
    @Parser
    def new_parser(stream: Sequence[T], index: int) -> Result:
        failures = []
        output = []
        for parser in parsers:
            result = parser(stream, index)
            if result.failures is not None:
                failures.append(result.failures)
            output.append(result.output)
            if result.is_success:
                index = result.current_index
                continue
            failure = furthest_failure(failures)
            return Result(tuple(output), index, False, failure)
        return Result(tuple(output), index, True, furthest_failure(failures))

    return new_parser


def alt(*parsers: 'Parser[T, Any]') -> 'Parser[T, Any]':
    parser: Parser[T, None] = fail('nothing')
    for p in parsers:
        parser |= p
    return parser


def fail(expected: str) -> Parser[T, None]:
    @Parser
    def parser(_: Sequence[T], index: int) -> Result[None]:
        failure = FailureTree(expected, index, [])
        return Result(None, index, False, failure)

    return parser


@Parser
def peek_prev(stream: Sequence[T], index: int) -> Result[T]:
    if index:
        return Result(stream[index - 1], index, True)
    return Result(
        None, index, False, FailureTree('not the start of file', index, [])
    )


def test_item(
    func: Callable[[T], bool], description: str
) -> Parser[T, Optional[T]]:
    @Parser
    def parser(stream: Sequence[T], index: int) -> Result[Optional[T]]:
        if index < len(stream) and func(stream[index]):
            return Result(stream[index], index + 1, True, None)
        return Result(None, index, False, FailureTree(description, index, []))

    return parser


ParserGeneratingFunction = Callable[[], Generator[Parser[T, Any], Any, V]]


@overload
def generate(
    desc_or_generator: str,
) -> Callable[[ParserGeneratingFunction[T, V]], Parser[T, V]]: ...


@overload
def generate(
    desc_or_generator: ParserGeneratingFunction[T, V],
) -> Parser[T, V]: ...


def generate(
    desc_or_generator: Union[str, ParserGeneratingFunction[T, V]],
) -> Union[
    Callable[[ParserGeneratingFunction[T, V]], Parser[T, V]],
    Parser[T, V],
]:
    if isinstance(desc_or_generator, str):
        return lambda generator: generate(generator).desc(desc_or_generator)

    @Parser
    def new_parser(stream: Sequence[T], index: int) -> Result[V]:
        failures = []
        iterator = desc_or_generator()
        results = []
        output = None
        try:
            while True:
                parser = iterator.send(output)
                result = parser(stream, index)
                results.append(result)
                output = result.output
                if not result.is_success:
                    result = cast(
                        Result[Any], _result_with_furthest_failure(results)
                    )
                    return Result(
                        result.output,
                        result.current_index,
                        False,
                        result.failures,
                    )
                if result.failures is not None:
                    failures.append(result.failures)
                index = result.current_index
        except StopIteration as e:
            return Result(e.value, index, True, furthest_failure(failures))

    return new_parser


def _result_with_furthest_failure(
    results: List[Result[T]],
) -> Optional[Result[T]]:
    furthest_index = -1
    ret = None
    for result in results:
        if (
            result.failures is not None
            and result.failures.furthest_index > furthest_index
        ):
            furthest_index = result.failures.furthest_index
            ret = result
    return ret
