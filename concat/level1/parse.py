"""The level one Concat parser.

This parser is designed to extend the level zero parser.
"""
from concat.level0.lex import Token
import concat.level0.parse
from typing import Iterable, List


class NoneWordNode(concat.level0.parse.WordNode):

    def __init__(self, none: Token):
        super().__init__()
        self.location = none.start
        self.children = []


class NotImplWordNode(concat.level0.parse.WordNode):

    def __init__(self, not_impl: Token):
        super().__init__()
        self.location = not_impl.start
        self.children = []


class EllipsisWordNode(concat.level0.parse.WordNode):

    def __init__(self, ellipsis: Token):
        super().__init__()
        self.location = ellipsis.start
        self.children = []


class SubscriptionWordNode(concat.level0.parse.WordNode):
    def __init__(self, children: Iterable[concat.level0.parse.WordNode]):
        super().__init__()
        self.children: List[concat.level0.parse.WordNode] = list(children)
        if self.children:
            self.location = self.children[0].location


def level_1_extension(parsers: concat.level0.parse.ParserDict) -> None:
    parsers['literal-word'] |= (
        parsers.ref_parser('none-word')
        | parsers.ref_parser('not-impl-word')
        | parsers.ref_parser('ellipsis-word')
    )

    # This parses a none word.
    # none word = NONE ;
    parsers['none-word'] = parsers.token('NONE').map(NoneWordNode)

    # This parses a not-impl word.
    # not-impl word = NOTIMPL ;
    parsers['not-impl-word'] = parsers.token('NOTIMPL').map(NotImplWordNode)

    # This parses an ellipsis word.
    # ellipsis word = ELLIPSIS ;
    parsers['ellipsis-word'] = parsers.token('ELLIPSIS').map(EllipsisWordNode)

    parsers['word'] |= parsers.ref_parser('subscription-word') | parsers.ref_parser('slice-word')

    # This parses a subscription word.
    # subscription word = LSQB, word*, RSQB ;
    parsers['subscription-word'] = parsers.token('LSQB') >> parsers.ref_parser('word').many().map(SubscriptionWordNode) << parsers.token('RSQB')
