"""Parser combinators for error recovery.

Inspired by chumsky:
https://github.com/zesterer/chumsky/blob/3c8488e5973c287399632a39c56fa3f3ed48d81c/src/recovery.rs.
"""

from concat.parser_combinators import (
    Parser,
    Result,
    furthest_failure,
    generate,
)
from typing import Any, Generator, List, Sequence, Tuple, TypeVar, Union

_T = TypeVar('_T')
_U = TypeVar('_U')
_V = TypeVar('_V')


def skip_until(p: Parser[_T, Any]) -> Parser[_T, List[_T]]:
    """Skip until a certain parser matches.

    Returns the tokens that were skipped. The current position will not be
    advanced past the match."""

    @Parser
    def parser(stream: Sequence[_T], index: int) -> Result[List[_T]]:
        original_index = index
        failures = []
        while index < len(stream):
            result = p(stream, index)
            if result.is_success:
                return Result(
                    list(stream[original_index:index]), index, True, None
                )
            assert result.failures is not None
            failures.append(result.failures)
            index += 1
        return Result(
            list(stream[original_index:]),
            index,
            False,
            furthest_failure(failures),
        )

    return parser


def bracketed(
    left: Parser[_T, Any], inside: Parser[_T, _U], right: Parser[_T, Any]
) -> Parser[_T, Union[_U, List[_T]]]:
    """Match a sequence wrapped by delimiters.

    The delimiters are used for error recovery.
    """

    @generate
    def parser() -> Generator:
        yield left
        output = yield recover(inside, skip_until(right))
        yield right
        return output

    return parser


def recover(
    p: Parser[_T, _U], fallback: Parser[_T, _V]
) -> Parser[_T, Union[_U, Tuple[_V, Result[_U]]]]:
    """Invoke a fallback parser where the first parser fails.

    If both parsers fail, the result of the first parser is returned."""

    @Parser
    def parser(
        stream: Sequence[_T], index: int
    ) -> Result[Union[_U, Tuple[_V, Result[_U]]]]:
        result = p(stream, index)
        if result.is_success:
            return result
        fallback_result = fallback(stream, index)
        if fallback_result.is_success:
            return Result(
                (fallback_result.output, result),
                fallback_result.current_index,
                True,
                fallback_result.failures,
            )
        return result

    return parser
