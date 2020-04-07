"""The level one Concat parser.

This parser is designed to extend the level zero parser.
"""
from concat.level0.lex import Token
import concat.level0.parse
import concat.level1.typecheck
from concat.astutils import Words, Location, WordsOrStatements, flatten
import concat.parser_combinators
import abc
import operator
from typing import Iterable, List, Tuple, Sequence, Optional, Generator
import parsy


# Patches to parsy for better errors--useful for debugging

class ParseError(parsy.ParseError):
    def line_info(self):
        return '{}:{} ({!r} here)'.format(
            *self.stream[self.index].start, self.stream[self.index])


# let's lie
parsy.ParseError = ParseError  # type: ignore


class SimpleValueWordNode(concat.level0.parse.WordNode, abc.ABC):
    def __init__(self, token: Token):
        super().__init__()
        self.location = token.start
        self.children = []


class NoneWordNode(SimpleValueWordNode):
    pass


class NotImplWordNode(SimpleValueWordNode):
    pass


class EllipsisWordNode(SimpleValueWordNode):
    pass


class TrueWordNode(SimpleValueWordNode):
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


class OperatorWordNode(concat.level0.parse.WordNode, abc.ABC):
    def __init__(self, token: concat.level0.lex.Token):
        super().__init__()
        self.children = []
        self.location = token.start


class SubtractWordNode(OperatorWordNode):
    pass


class PowerWordNode(OperatorWordNode):
    pass


class InvertWordNode(OperatorWordNode):
    pass


class MulWordNode(OperatorWordNode):
    pass


class MatMulWordNode(OperatorWordNode):
    pass


class FloorDivWordNode(OperatorWordNode):
    pass


class DivWordNode(OperatorWordNode):
    pass


class ModWordNode(OperatorWordNode):
    pass


class AddWordNode(OperatorWordNode):
    pass


class LeftShiftWordNode(OperatorWordNode):
    pass


class RightShiftWordNode(OperatorWordNode):
    pass


class BitwiseAndWordNode(OperatorWordNode):
    pass


class BitwiseXorWordNode(OperatorWordNode):
    pass


class BitwiseOrWordNode(OperatorWordNode):
    pass


class LessThanWordNode(OperatorWordNode):
    pass


class GreaterThanWordNode(OperatorWordNode):
    pass


class EqualToWordNode(OperatorWordNode):
    pass


class GreaterThanOrEqualToWordNode(OperatorWordNode):
    pass


class LessThanOrEqualToWordNode(OperatorWordNode):
    pass


class NotEqualToWordNode(OperatorWordNode):
    pass


class IsWordNode(OperatorWordNode):
    pass


class InWordNode(OperatorWordNode):
    pass


class OrWordNode(OperatorWordNode):
    pass


class AndWordNode(OperatorWordNode):
    pass


class NotWordNode(OperatorWordNode):
    pass


class BytesWordNode(concat.level0.parse.WordNode):
    def __init__(self, bytes: concat.level0.lex.Token):
        super().__init__()
        self.children = []
        self.location = bytes.start
        self.value = eval(bytes.value)


class IterableWordNode(concat.level0.parse.WordNode, abc.ABC):
    def __init__(self, element_words: Iterable[Words], location: Location):
        super().__init__()
        self.children = []
        self.location = location
        for children in element_words:
            self.children += list(children)


class TupleWordNode(IterableWordNode):
    def __init__(self, element_words: Iterable[Words], location: Location):
        super().__init__(element_words, location)
        self.tuple_children = element_words


class ListWordNode(IterableWordNode):
    def __init__(self, element_words: Iterable[Words], location: Location):
        super().__init__(element_words, location)
        self.list_children = element_words


class SetWordNode(IterableWordNode):
    def __init__(self, element_words: Iterable[Words], location: Location):
        super().__init__(element_words, location)
        self.set_children = element_words


class DelStatementNode(concat.level0.parse.StatementNode):
    def __init__(self, targets: Sequence[concat.level0.parse.WordNode]):
        super().__init__()
        self.children = targets
        self.location = targets[0].location


class DictWordNode(IterableWordNode):
    def __init__(
        self, element_words: Iterable[Iterable[Words]], location: Location
    ):
        flattened_pairs = self.__flatten_pairs(element_words)
        super().__init__(flattened_pairs, location)
        self.dict_children = element_words

    @staticmethod
    def __flatten_pairs(
        element_words: Iterable[Iterable[Words]]
    ) -> Iterable[Words]:
        for key, value in element_words:
            yield key
            yield value


class SimpleKeywordWordNode(concat.level0.parse.WordNode, abc.ABC):
    def __init__(self, token: Token):
        self.location = token.start
        self.children = []


class YieldWordNode(SimpleKeywordWordNode):
    pass


class AwaitWordNode(SimpleKeywordWordNode):
    pass


class AssertWordNode(SimpleKeywordWordNode):
    pass


class RaiseWordNode(SimpleKeywordWordNode):
    pass


class TryWordNode(SimpleKeywordWordNode):
    pass


class WithWordNode(SimpleKeywordWordNode):
    pass


class FuncdefStatementNode(concat.level0.parse.StatementNode):
    def __init__(
        self,
        name: Token,
        decorators: Iterable[concat.level0.parse.WordNode],
        annotation: Optional[Iterable[concat.level0.parse.WordNode]],
        body: WordsOrStatements,
        location: Location,
        stack_effect: Optional[concat.level1.typecheck.StackEffect] = None
    ):
        self.location = location
        self.name = name.value
        self.decorators = decorators
        self.annotation = annotation
        self.body = body
        self.children = [
            *self.decorators, *(self.annotation or []), *self.body]
        self.stack_effect = stack_effect


class AsyncFuncdefStatementNode(FuncdefStatementNode):
    pass


class ImportStatementNode(concat.level0.parse.ImportStatementNode):
    def __init__(
        self,
        module: str,
        asname: Optional[str] = None,
        location: Location = (0, 0)
    ):
        token = Token()
        token.value = module
        super().__init__(token, location)
        self.asname = asname


class FromImportStatementNode(ImportStatementNode):
    def __init__(
        self,
        relative_module: str,
        imported_name: str,
        asname: Optional[str] = None,
        location: Location = (0, 0)
    ):
        super().__init__(relative_module, asname, location)
        self.imported_name = imported_name


class FromImportStarStatementNode(FromImportStatementNode):
    def __init__(self, module: str, location: Location = (0, 0)):
        super().__init__(module, '*', None, location)


class ClassdefStatementNode(concat.level0.parse.StatementNode):
    def __init__(
        self,
        name: str,
        body: WordsOrStatements,
        location: Location,
        decorators: Optional[Words] = None,
        bases: Iterable[Words] = (),
        keyword_args: Iterable[Tuple[str, concat.level0.parse.WordNode]] = ()
    ):
        super().__init__()
        self.location = location
        self.children = body
        self.class_name = name
        self.decorators = [] if decorators is None else decorators
        self.bases = bases
        self.keyword_args = keyword_args


def level_1_extension(parsers: concat.level0.parse.ParserDict) -> None:
    parsers['literal-word'] |= parsy.alt(
        parsers.ref_parser('none-word'),
        parsers.ref_parser('not-impl-word'),
        parsers.ref_parser('ellipsis-word'),
        parsers.ref_parser('bytes-word'),
        parsers.ref_parser('tuple-word'),
        parsers.ref_parser('list-word'),
        parsers.ref_parser('set-word'),
        parsers.ref_parser('dict-word'),
        parsers.ref_parser('true-word')
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
        parsers.ref_parser('await-word'),
        parsers.ref_parser('assert-word'),
        parsers.ref_parser('raise-word'),
        parsers.ref_parser('try-word'),
        parsers.ref_parser('with-word')
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

    parsers['operator-word'] = parsy.alt(
        parsers.ref_parser('subtract-word'),
        parsers.ref_parser('power-word'),
        parsers.ref_parser('invert-word'),
        parsers.ref_parser('mul-word'),
        parsers.ref_parser('mat-mul-word'),
        parsers.ref_parser('floor-div-word'),
        parsers.ref_parser('div-word'),
        parsers.ref_parser('mod-word'),
        parsers.ref_parser('add-word'),
        parsers.ref_parser('left-shift-word'),
        parsers.ref_parser('right-shift-word'),
        parsers.ref_parser('bitwise-and-word'),
        parsers.ref_parser('bitwise-xor-word'),
        parsers.ref_parser('bitwise-or-word'),
        parsers.ref_parser('less-than-word'),
        parsers.ref_parser('greater-than-word'),
        parsers.ref_parser('equal-to-word'),
        parsers.ref_parser('greater-than-or-equal-to-word'),
        parsers.ref_parser('less-than-or-equal-to-word'),
        parsers.ref_parser('not-equal-to-word'),
        parsers.ref_parser('is-word'),
        parsers.ref_parser('in-word'),
        parsers.ref_parser('or-word'),
        parsers.ref_parser('and-word'),
        parsers.ref_parser('not-word')
    )

    operators = (
        ('power', 'DOUBLESTAR', PowerWordNode),
        ('subtract', 'MINUS', SubtractWordNode),
        ('mul', 'STAR', MulWordNode),
        ('mat-mul', 'AT', MatMulWordNode),
        ('floor-div', 'DOUBLESLASH', FloorDivWordNode),
        ('div', 'SLASH', DivWordNode),
        ('mod', 'PERCENT', ModWordNode),
        ('add', 'PLUS', AddWordNode),
        ('left-shift', 'LEFTSHIFT', LeftShiftWordNode),
        ('right-shift', 'RIGHTSHIFT', RightShiftWordNode),
        ('bitwise-and', 'AMPER', BitwiseAndWordNode),
        ('bitwise-xor', 'CIRCUMFLEX', BitwiseXorWordNode),
        ('bitwise-or', 'VBAR', BitwiseOrWordNode),
        ('invert', 'TILDE', InvertWordNode),
        ('less-than', 'LESS', LessThanWordNode),
        ('greater-than', 'GREATER', GreaterThanWordNode),
        ('equal-to', 'EQEQUAL', EqualToWordNode),
        (
            'greater-than-or-equal-to',
            'GREATEREQUAL',
            GreaterThanOrEqualToWordNode
        ),
        ('less-than-or-equal-to', 'LESSEQUAL', LessThanOrEqualToWordNode),
        ('not-equal-to', 'NOTEQUAL', NotEqualToWordNode),
        ('is', 'IS', IsWordNode),
        # there is not 'is not'; instead we have 'is' and 'not'
        ('in', 'IN', InWordNode),
        # there is not 'not in'; instead we have 'in' and 'not'
        ('or', 'OR', OrWordNode),
        ('and', 'AND', AndWordNode),
        ('not', 'NOT', NotWordNode)
    )

    for operator_name, token_type, node_type in operators:
        parser_name = operator_name + '-word'
        parsers[parser_name] = parsers.token(token_type).map(node_type)

    # This parses a bytes word.
    # bytes word = BYTES ;
    parsers['bytes-word'] = parsers.token('BYTES').map(BytesWordNode)

    # This parses a tuple word.
    # tuple word = LPAR, word list, RPAR ;
    @parsy.generate('tuple word')
    def tuple_word_parser() -> Generator:
        location = (yield parsers.token('LPAR')).start
        element_words = yield word_list_parser
        yield parsers.token('RPAR')
        return TupleWordNode(element_words, location)

    parsers['tuple-word'] = tuple_word_parser

    # This parses a list word.
    # list word = LSQB, word list, RSQB ;
    @parsy.generate('list word')
    def list_word_parser() -> Generator:
        location = (yield parsers.token('LSQB')).start
        element_words = yield word_list_parser
        end = parsers.token('RSQB')
        yield end
        return ListWordNode(element_words, location)

    parsers['list-word'] = list_word_parser

    # word list = (COMMA | word+, COMMA | word+, (COMMA, word+)+, [ COMMA ]) ;
    @parsy.generate('word list')
    def word_list_parser() -> Generator:
        empty: 'parsy.Parser[Token, List[Words]]' = parsers.token(
            'COMMA').result([])
        singleton = parsy.seq(parsers['word'].at_least(
            1) << parsers.token('COMMA'))
        multiple_element = parsers['word'].at_least(1).sep_by(
            parsers.token('COMMA'), min=2) << parsers.token('COMMA').optional()
        element_words = yield (multiple_element | singleton | empty)
        return element_words

    # This parses a set word.
    # list word = LBRACE, word list, RBRACE ;
    @parsy.generate('set word')
    def set_word_parser():
        location = (yield parsers.token('LBRACE')).start
        element_words = yield word_list_parser
        yield parsers.token('RBRACE')
        return SetWordNode(element_words, location)

    parsers['set-word'] = set_word_parser

    # This parses a dict word.
    # dict word =
    #   LBRACE,
    #   [ key-value pair, (COMMA, key-value pair)* ],
    #   [ COMMA ],
    #   RBRACE ;
    # key-value pair = word*, COLON, word* ;
    @parsy.generate('dict word')
    def dict_word_parser() -> Generator:
        location = (yield parsers.token('LBRACE')).start
        elements = key_value_pair.sep_by(parsers.token(
            'COMMA'), min=0) << parsers.token('COMMA').optional()
        element_words = yield elements
        yield parsers.token('RBRACE')
        return DictWordNode(element_words, location)

    parsers['dict-word'] = dict_word_parser

    key_value_pair = parsy.seq(parsers.ref_parser('word').many(
    ) << parsers.token('COLON'), parsers.ref_parser('word').many())

    parsers['true-word'] = parsers.token('TRUE').map(TrueWordNode)

    parsers['yield-word'] = parsers.token('YIELD').map(YieldWordNode)

    parsers['await-word'] = parsers.token('AWAIT').map(AwaitWordNode)

    parsers['assert-word'] = parsers.token('ASSERT').map(AssertWordNode)

    parsers['raise-word'] = parsers.token('RAISE').map(RaiseWordNode)

    parsers['try-word'] = parsers.token('TRY').map(TryWordNode)

    parsers['with-word'] = parsers.token('WITH').map(WithWordNode)

    parsers['statement'] |= parsy.alt(
        parsers.ref_parser('del-statement'),
        parsers.ref_parser('async-funcdef-statement'),
        parsers.ref_parser('classdef-statement'),
        parsers.ref_parser('funcdef-statement')
    )

    # Parsers a del statement.
    # del statement = DEL, target words ;
    # target words = target word, (COMMA, target word)*, [ COMMA ] ;
    # target word = name word
    #   | LPAR, target words, RPAR
    #   | LSQB, target words, RQSB
    #   | attribute word
    #   | subscription word
    #   | slice word ;
    parsers['del-statement'] = parsers.token(
        'DEL') >> parsers.ref_parser('target-words').map(DelStatementNode)

    parsers['target-words'] = (parsers.ref_parser('target-word').sep_by(
        parsers.token('COMMA'), min=1) << parsers.token('COMMA').optional()
    ).map(flatten)

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
    # async funcdef statement = ASYNC, funcdef statement ;
    @parsy.generate('async funcdef statement')
    def async_funcdef_statement_parser() -> Generator:
        location = (yield parsers.token('ASYNC')).start
        func: FuncdefStatementNode = (yield parsers['funcdef-statement'])
        name = Token()
        name.value = func.name
        return AsyncFuncdefStatementNode(
            name,
            func.decorators,
            func.annotation,
            func.body,
            location,
            func.stack_effect
        )

    parsers['async-funcdef-statement'] = async_funcdef_statement_parser

    # This parses a function definition.
    # funcdef statement = DEF, NAME, [ LPAR, stack effect, RPAR ], decorator*,
    #   [ annotation ], COLON, suite ;
    # decorator = AT, word ;
    # annotation = RARROW, word* ;
    # suite = word* | statement
    #   | NEWLINE, INDENT, (word | statement, NEWLINE)+, DEDENT ;
    # The stack effect syntax is defined within the .typecheck module.
    @parsy.generate
    def funcdef_statement_parser() -> Generator:
        location = (yield parsers.token('DEF')).start
        name = yield parsers.token('NAME')
        effect_tokens = None
        if (yield parsers.token('LPAR').optional()):
            effect_tokens = []
            while not (yield parsers.token('RPAR').optional()):
                effect_tokens.append((yield parsy.any_char))
        if effect_tokens is None:
            effect = None
        else:
            effect = concat.level1.typecheck.parse_stack_effect(effect_tokens)
        decorators = yield decorator.many()
        annotation = yield annotation_parser.optional()
        yield parsers.token('COLON')
        body = yield suite
        return FuncdefStatementNode(
            name, decorators, annotation, body, location, effect)

    parsers['funcdef-statement'] = concat.parser_combinators.desc_cumulatively(
        funcdef_statement_parser, 'funcdef statement')

    decorator = parsers.token('AT') >> parsers.ref_parser('word')

    annotation_parser = parsers.token(
        'RARROW') >> parsers.ref_parser('word').many()

    @parsy.generate('suite')
    def suite():
        words = parsers['word'].many()
        statement = parsy.seq(parsers['statement'])
        block_content = (parsers['word'] | parsers['statement']
                         << parsers.token('NEWLINE')).at_least(1)
        indented_block = parsers.token('NEWLINE') >> parsers.token(
            'INDENT') >> block_content << parsers.token('DEDENT')
        return (yield words | statement | indented_block)

    @parsy.generate('module')
    def module():
        name = parsers.token('NAME').map(operator.attrgetter('value'))
        return (yield name.sep_by(parsers.token('DOT'), min=1).concat())

    # These following parsers parse import statements.
    # import statement = IMPORT, module, [ AS, NAME ]
    #   | FROM, relative module, IMPORT, NAME, [ AS, NAME ]
    #   | FROM, module, IMPORT, STAR;
    # module = NAME, (DOT, NAME)* ;
    # relative module = DOT*, module | DOT+ ;

    @parsy.generate('import statement')
    def import_statement_parser() -> Generator:
        location = (yield parsers.token('IMPORT')).start
        module_name = yield module
        asname_parser = parsers.token('NAME').map(operator.attrgetter('value'))
        asname = None
        if (yield parsers.token('AS').optional()):
            asname = yield asname_parser
        return ImportStatementNode(module_name, asname, location)

    parsers['import-statement'] = import_statement_parser

    @parsy.generate('relative module')
    def relative_module():
        dot = parsers.token('DOT').map(operator.attrgetter('value'))
        return (yield (dot.many().concat() + module) | dot.at_least(1))

    @parsy.generate('from-import statement')
    def from_import_statement_parser() -> Generator:
        location = (yield parsers.token('FROM')).start
        module = yield relative_module
        name_parser = parsers.token('NAME').map(operator.attrgetter('value'))
        imported_name = yield parsers.token('IMPORT') >> name_parser
        asname = None
        if (yield parsers.token('AS').optional()):
            asname = yield name_parser
        return FromImportStatementNode(module, imported_name, asname, location)

    parsers['import-statement'] |= from_import_statement_parser

    @parsy.generate('from-import-star statement')
    def from_import_star_statement_parser() -> Generator:
        location = (yield parsers.token('FROM')).start
        module_name = yield module
        yield parsers.token('IMPORT')
        yield parsers.token('STAR')
        return FromImportStarStatementNode(module_name, location)

    parsers['import-statement'] |= from_import_star_statement_parser

    # This parses a class definition statement.
    # classdef statement = CLASS, NAME, decorator*, [ bases ], keyword arg*,
    #   COLON, suite ;
    # bases = tuple word ;
    # keyword arg = NAME, EQUAL, word ;
    @parsy.generate('classdef statement')
    def classdef_statement_parser():
        location = (yield parsers.token('CLASS')).start
        name_token = yield parsers.token('NAME')
        decorators = yield decorator.many()
        bases_list = yield bases.optional()
        keyword_args = yield keyword_arg.map(tuple).many()
        yield parsers.token('COLON')
        body = yield suite
        return ClassdefStatementNode(
            name_token.value,
            body,
            location,
            decorators,
            bases_list,
            keyword_args
        )

    parsers['classdef-statement'] = classdef_statement_parser

    bases = parsers.ref_parser(
        'tuple-word').map(operator.attrgetter('tuple_children'))

    keyword_arg = parsy.seq(parsers.token('NAME').map(operator.attrgetter(
        'value')) << parsers.token('EQUAL'), parsers.ref_parser('word'))
