"""The level one Concat parser.

This parser is designed to extend the level zero parser.
"""
from concat.level0.lex import Token
import concat.level0.parse
from typing import Iterable, List, Tuple, Sequence, Optional, Union
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


class IterableWordNode(abc.ABC, concat.level0.parse.WordNode):
    def __init__(self, element_words: Iterable[Iterable[concat.level0.parse.WordNode]], location: Tuple[int, int]):
        super().__init__()
        self.children = []
        self.location = location
        for children in element_words:
            self.children += list(children)


class TupleWordNode(concat.level0.parse.WordNode):
    def __init__(self, element_words: Iterable[Iterable[concat.level0.parse.WordNode]], location: Tuple[int, int]):
        super().__init__()
        self.tuple_children = element_words
        self.children = []
        self.location = location
        for children in self.tuple_children:
            self.children += list(children)


class ListWordNode(concat.level0.parse.WordNode):
    def __init__(self, element_words: Iterable[Iterable[concat.level0.parse.WordNode]], location: Tuple[int, int]):
        super().__init__()
        self.list_children = element_words
        self.children = []
        self.location = location
        for children in self.list_children:
            self.children += list(children)


class SetWordNode(IterableWordNode):
    def __init__(self, element_words: Iterable[Iterable[concat.level0.parse.WordNode]], location: Tuple[int, int]):
        super().__init__(element_words, location)
        self.set_children = element_words


class DelStatementNode(concat.level0.parse.StatementNode):
    def __init__(self, targets: Sequence[concat.level0.parse.WordNode]):
        super().__init__()
        self.children = targets
        self.location = targets[0].location


class DictWordNode(IterableWordNode):
    def __init__(self, element_words: Iterable[Iterable[Iterable[concat.level0.parse.WordNode]]], location: Tuple[int, int]):
        flattened_pairs = self.__flatten_pairs(element_words)
        super().__init__(flattened_pairs, location)
        self.dict_children = element_words

    @staticmethod
    def __flatten_pairs(element_words: Iterable[Iterable[Iterable[concat.level0.parse.WordNode]]]) -> Iterable[Iterable[concat.level0.parse.WordNode]]:
        for key, value in element_words:
            yield key
            yield value


class YieldWordNode(concat.level0.parse.WordNode):
    def __init__(self, token: Token):
        self.location = token.start
        self.children = []


class AwaitWordNode(concat.level0.parse.WordNode):
    def __init__(self, token: Token):
        self.location = token.start
        self.children = []


class AsyncFuncdefStatementNode(concat.level0.parse.StatementNode):
    def __init__(self, name: Token, decorators: Iterable[concat.level0.parse.WordNode], annotation: Optional[Iterable[concat.level0.parse.WordNode]], body: Iterable[Union[concat.level0.parse.WordNode, concat.level0.parse.StatementNode]], location: Tuple[int, int]):
        self.location = location
        self.name = name.value
        self.decorators = decorators
        self.annotation = annotation
        self.body = body
        self.children = [*self.decorators, *
                         (self.annotation or []), *self.body]


def level_1_extension(parsers: concat.level0.parse.ParserDict) -> None:
    parsers['literal-word'] |= parsy.alt(
        parsers.ref_parser('none-word'),
        parsers.ref_parser('not-impl-word'),
        parsers.ref_parser('ellipsis-word'),
        parsers.ref_parser('bytes-word'),
        parsers.ref_parser('tuple-word'),
        parsers.ref_parser('list-word'),
        parsers.ref_parser('set-word'),
        parsers.ref_parser('dict-word')
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

    parsers['word'] |= parsy.alt(
        parsers.ref_parser('subscription-word'),
        parsers.ref_parser('slice-word'),
        parsers.ref_parser('operator-word'),
        parsers.ref_parser('yield-word'),
        parsers.ref_parser('await-word')
    )

    # This parses a subscription word.
    # subscription word = LSQB, word*, RSQB ;
    parsers['subscription-word'] = parsers.token('LSQB') >> parsers.ref_parser(
        'word').many().map(SubscriptionWordNode) << parsers.token('RSQB')

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

    # This parses a list word.
    # list word = LSQB, ([ word* ], COMMA | word+, (COMMA, word+)+, [ COMMA ]), RSQB ;
    @parsy.generate('list word')
    def list_word_parser():
        # TODO: reflect the grammar in the code better
        location = (yield parsers.token('LSQB')).start
        element_words = []
        element_words.append((yield parsers['word'].many()))
        yield parsers.token('COMMA')
        if (yield parsers.token('RSQB').optional()):
            # 0 or 1-length list
            length = 1 if element_words[0] else 0
            return ListWordNode(element_words[0:length], location)
        # >= 2-length lists; there must be no 'empty words'
        if not element_words[0]:
            yield parsy.fail('word before first comma in list longer than 1')
        element_words.append((yield parsers['word'].at_least(1)))
        element_words += (yield (parsers.token('COMMA') >> parsers['word'].at_least(1)).many())
        yield parsers.token('COMMA').optional()
        yield parsers.token('RSQB')
        return ListWordNode(element_words, location)

    parsers['list-word'] = list_word_parser

    @parsy.generate('word list')
    def word_list_parser():
        element_words = []
        element_words.append((yield parsers['word'].many()))
        yield parsers.token('COMMA')
        if (yield parsers.token('RPAR').optional()):
            # 0 or 1-length tuple
            length = 1 if element_words[0] else 0
            return element_words[0:length]
        # >= 2-length tuples; there must be no 'empty words'
        if not element_words[0]:
            yield parsy.fail('word before first comma in tuple longer than 1')
        element_words.append((yield parsers['word'].at_least(1)))
        element_words += (yield (parsers.token('COMMA') >> parsers['word'].at_least(1)).many())
        yield parsers.token('COMMA').optional()
        return element_words

    # This parses a set word.
    # list word = LBRACE, word list, RBRACE ;
    # word list = ([ word* ], COMMA | word+, (COMMA, word+)+, [ COMMA ]) ;
    @parsy.generate('set word')
    def set_word_parser():
        location = (yield parsers.token('LBRACE')).start
        element_words = yield word_list_parser
        yield parsers.token('RBRACE')
        return SetWordNode(element_words, location)

    parsers['set-word'] = set_word_parser

    # This parses a dict word.
    # dict word = LBRACE, ([ key-value pair ], COMMA | key-value pair, (COMMA, key-value pair)+, [ COMMA ]), RBRACE ;
    # key-value pair = word*, COLON, word* ;
    @parsy.generate('dict word')
    def dict_word_parser():
        # TODO: reflect the grammar in the code better
        location = (yield parsers.token('LBRACE')).start
        element_words = []
        element_words.append((yield key_value_pair.optional()))
        yield parsers.token('COMMA')
        if (yield parsers.token('RBRACE').optional()):
            # 0 or 1-length list
            length = 1 if element_words[0] else 0
            return DictWordNode(element_words[0:length], location)
        # >= 2-length lists; there must be no 'empty words'
        if not element_words[0]:
            yield parsy.fail('key-value pair before first comma in dict longer than 1')
        element_words.append((yield key_value_pair))
        element_words += (yield (parsers.token('COMMA') >> key_value_pair).many())
        yield parsers.token('COMMA').optional()
        yield parsers.token('RBRACE')
        return DictWordNode(element_words, location)

    parsers['dict-word'] = dict_word_parser

    key_value_pair = parsy.seq(parsers.ref_parser('word').many(
    ) << parsers.token('COLON'), parsers.ref_parser('word').many())

    parsers['yield-word'] = parsers.token('YIELD').map(YieldWordNode)

    parsers['await-word'] = parsers.token('AWAIT').map(AwaitWordNode)

    parsers['statement'] |= parsy.alt(
        parsers.ref_parser('del-statement'),
        parsers.ref_parser('async-funcdef-statement'),
    )

    # Parsers a del statement.
    # del statement = DEL, target words ;
    # target words = target word, (COMMA, target word)*, [ COMMA ] ;
    # target word = name word | LPAR, target words, RPAR | LSQB, target words, RQSB | attribute word | subscription word | slice word ;
    parsers['del-statement'] = parsers.token(
        'DEL') >> parsers.ref_parser('target-words').map(DelStatementNode)

    # TODO: flatten
    parsers['target-words'] = parsy.seq(parsers.ref_parser('target-word')) + (parsers.token(
        'COMMA') >> parsers.ref_parser('target-word')).many() << parsers.token('COMMA').optional()  # type: ignore

    parsers['target-word'] = parsy.alt(
        parsers.ref_parser('name-word'),
        parsers.token('LPAR') >> parsers.ref_parser(
            'target-words') << parsers.token('RPAR'),
        parsers.token('LSQB') >> parsers.ref_parser(
            'target-words') << parsers.token('RSQB'),
        parsers.ref_parser('attribute-word'),
        parsers.ref_parser('subscription-word'),
        parsers.ref_parser('slice-word')
    )

    # This parses an async function definition.
    # async funcdef statement = ASYNC, DEF, NAME, decorator*, [ annotation ], COLON, suite ;
    # decorator = AT, word ;
    # annotation = RARROW, word* ;
    # suite = word* | statement | NEWLINE, INDENT, (word | statement, NEWLINE)+, DEDENT ;
    @parsy.generate('async funcdef statement')
    def async_funcdef_statement_parser():
        location = (yield parsers.token('ASYNC')).start
        yield parsers.token('DEF')
        name = yield parsers.token('NAME')
        decorators = yield decorator.many()
        annotation = yield annotation_parser.optional()
        yield parsers.token('COLON')
        body = yield suite
        return AsyncFuncdefStatementNode(name, decorators, annotation, body, location)

    parsers['async-funcdef-statement'] = async_funcdef_statement_parser
