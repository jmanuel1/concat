"""The level one Concat parser.

This parser is designed to extend the level zero parser.
"""
from concat.level0.lex import Token
import concat.level0.parse
from typing import Iterable, List
import parsy


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


class SliceWordNode(concat.level0.parse.WordNode):
    def __init__(self, children: Iterable[Iterable[concat.level0.parse.WordNode]]):
        super().__init__()
        self.start_children, self.stop_children, self.step_children = children
        self.children = [*self.start_children, *self.stop_children, *self.step_children]
        if self.children:
            self.location = self.children[0]


class OperatorWordNode(concat.level0.parse.WordNode):
    pass


class MinusWordNode(OperatorWordNode):
    def __init__(self, minus: concat.level0.lex.Token):
        super().__init__()
        self.children = []
        self.location = minus.start


class BytesWordNode(concat.level0.parse.WordNode):
    def __init__(self, bytes: concat.level0.lex.Token):
        super().__init__()
        self.children = []
        self.location = bytes.start
        self.value = eval(bytes.value)
def level_1_extension(parsers: concat.level0.parse.ParserDict) -> None:
    parsers['literal-word'] |= parsy.alt(
        parsers.ref_parser('none-word'),
        parsers.ref_parser('not-impl-word'),
        parsers.ref_parser('ellipsis-word'),
        parsers.ref_parser('bytes-word'),
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

    parsers['word'] |= parsers.ref_parser('subscription-word') | parsers.ref_parser('slice-word') | parsers.ref_parser('operator-word')

    # This parses a subscription word.
    # subscription word = LSQB, word*, RSQB ;
    parsers['subscription-word'] = parsers.token('LSQB') >> parsers.ref_parser('word').many().map(SubscriptionWordNode) << parsers.token('RSQB')

    # This parses a slice word.
    # slice word = LSQB, word*, COLON, word*, [ COLON, word* ], RSQB ;
    @parsy.generate('slice word')
    def slice_word_parser():
        yield parsers.token('LSQB')
        start = yield parsers.ref_parser('word').many()
        yield parsers.token('COLON')
        stop = yield parsers.ref_parser('word').many()
        none = concat.level0.lex.Token()
        none.type = 'NONE'
        step = [NoneWordNode(none)]
        if (yield parsers.token('COLON').optional()):
            step = yield parsers['word'].many()
        yield parsers.token('RSQB')
        return SliceWordNode([start, stop, step])

    parsers['slice-word'] = slice_word_parser

    parsers['operator-word'] = parsers.ref_parser('minus-word')

    parsers['minus-word'] = parsers.token('MINUS').map(MinusWordNode)

    # This parses a bytes word.
    # bytes word = BYTES ;
    parsers['bytes-word'] = parsers.token('BYTES').map(BytesWordNode)
