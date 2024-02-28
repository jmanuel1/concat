import concat.parser_combinators
from typing import Callable, Dict, Sequence, TypeVar, TYPE_CHECKING


if TYPE_CHECKING:
    from concat.lex import Token
    from concat.parse import TopLevelNode


T = TypeVar('T')


class ParserDict(Dict[str, concat.parser_combinators.Parser]):
    """A dictionary to hold named references to parsers.

    These references can be indirect, meaning you can add a new alternative to
    a parser, and the other parsers that use it will pick up that change.
    """

    def extend_with(self: T, extension: Callable[[T], None]) -> None:
        extension(self)

    def parse(self, tokens: Sequence['Token']) -> 'TopLevelNode':
        return self['top-level'].parse(list(tokens))

    def ref_parser(self, name: str) -> concat.parser_combinators.Parser:
        @concat.parser_combinators.generate
        def parser():
            return (yield self[name])

        return parser
