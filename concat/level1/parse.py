"""The level one Concat parser.

This parser is designed to extend the level zero parser.
"""
from concat.level0.lex import Token
import concat.level0.parse


class NoneWordNode(concat.level0.parse.WordNode):

    def __init__(self, none: Token):
        self.location = none.start
        self.children = []


class NotImplWordNode(concat.level0.parse.WordNode):

    def __init__(self, not_impl: Token):
        self.location = not_impl.start
        self.children = []


class EllipsisWordNode(concat.level0.parse.WordNode):

    def __init__(self, ellipsis: Token):
        self.location = ellipsis.start
        self.children = []


def level_1_extension(parsers: concat.level0.parse.ParserDict) -> None:
    parsers['literal-word'] |= parsers.ref_parser(
        'none-word') | parsers.ref_parser('not-impl-word') | parsers.ref_parser('ellipsis-word')

    # This parses a none word.
    # none word = NONE ;
    parsers['none-word'] = parsers.token('NONE').map(NoneWordNode)

    # This parses a not-impl word.
    # not-impl word = NOTIMPL ;
    parsers['not-impl-word'] = parsers.token('NOTIMPL').map(NotImplWordNode)

    # This parses an ellipsis word.
    # ellipsis word = ELLIPSIS ;
    parsers['ellipsis-word'] = parsers.token('ELLIPSIS').map(EllipsisWordNode)
