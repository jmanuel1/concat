"""The level one Concat parser.

This parser is designed to extend the level zero parser.
"""
from concat.level0.lex import Token
import concat.level0.parse
from typing import Iterable, List, Tuple, Sequence
import abc
import parsy


class SingletonWordNode(abc.ABC, concat.level0.parse.WordNode):
    def __init__(self, token: Token):
        super().__init__()
        self.location = token.start
        self.children = []


class NoneWordNode(SingletonWordNode):
    pass


class NotImplWordNode(SingletonWordNode):
    pass


class EllipsisWordNode(SingletonWordNode):
    pass


class SubscriptionWordNode(concat.level0.parse.WordNode):
    def __init__(self, children: Iterable[concat.level0.parse.WordNode]):
        super().__init__()
        self.children: List[concat.level0.parse.WordNode] = list(children)
        if self.children:
            self.location = self.children[0].location


class SliceWordNode(concat.level0.parse.WordNode):
    def __init__(
        self,
        children: Iterable[Iterable[concat.level0.parse.WordNode]]
    ):
        super().__init__()
        self.start_children, self.stop_children, self.step_children = children
        self.children = [*self.start_children,
                         *self.stop_children, *self.step_children]
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
class TupleWordNode(concat.level0.parse.WordNode):
    def __init__(self, element_words: Iterable[Iterable[concat.level0.parse.WordNode]], location: Tuple[int, int]):
        super().__init__()
        self.tuple_children = element_words
        self.children = []
        self.location = location
        for children in self.tuple_children:
            self.children += list(children)


def level_1_extension(parsers: concat.level0.parse.ParserDict) -> None:
    parsers['literal-word'] |= parsy.alt(
        parsers.ref_parser('none-word'),
        parsers.ref_parser('not-impl-word'),
        parsers.ref_parser('ellipsis-word'),
        parsers.ref_parser('bytes-word'),
        parsers.ref_parser('tuple-word'),
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

    # This parses a tuple word.
    # tuple word = LPAR, ([ word* ], COMMA | word+, (COMMA, word+)+, [ COMMA ]), RPAR ;
    @parsy.generate('tuple word')
    def tuple_word_parser():
        # TODO: reflect the grammar in the code better
        location = (yield parsers.token('LPAR')).start
        element_words = []
        element_words.append((yield parsers['word'].many()))
        yield parsers.token('COMMA')
        if (yield parsers.token('RPAR').optional()):
            # 0 or 1-length tuple
            length = 1 if element_words[0] else 0
            return TupleWordNode(element_words[0:length], location)
        # >= 2-length tuples; there must be no 'empty words'
        if not element_words[0]:
            yield parsy.fail('word before first comma in tuple longer than 1')
        element_words.append((yield parsers['word'].at_least(1)))
        element_words += (yield (parsers.token('COMMA') >> parsers['word'].at_least(1)).many())
        yield parsers.token('COMMA').optional()
        yield parsers.token('RPAR')
        return TupleWordNode(element_words, location)

    parsers['tuple-word'] = tuple_word_parser
