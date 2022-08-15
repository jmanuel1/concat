"""The Concat parser.

On Extensibility:

The parser uses parsy, a parser combinator library. A custom parser
primitive is used to call the lexer.

- The extension mechanism:
Assume there is an existing word parser, like:

# import * parser module

def word_ext(parsers):
    parsers['word'] |= extensionParser

extendedParsers = parsers.extend_with(word_ext)

The parsers object is a dictionary with a few methods:
extend_with(extension) -- mutates the dictionary by adding the extension

- Other possible approaches:
Hand-written recursive descent parser that tries extensions when throwing an
exception: I would have to implement indefinte backtracking myself to have
well-defined extension points. Libraries like pyparsing would do that for me.

parsy is used instead of pyparsing since it supports having a separate
tokenization phase.
"""
import abc
import operator
from typing import (
    Iterable,
    Optional,
    Type,
    TypeVar,
    Any,
    Sequence,
    Tuple,
    Dict,
    Generator,
    List,
    Callable,
    TYPE_CHECKING,
)
import concat.lex
import concat.astutils
from concat.parser_combinators import desc_cumulatively
import parsy

if TYPE_CHECKING:
    from concat.lex import Token
    from concat.typecheck import TypeSequenceNode
    from concat.astutils import Location, Words, WordsOrStatements


class Node(abc.ABC):
    @abc.abstractmethod
    def __init__(self):
        self.location = (0, 0)
        self.children: Iterable[Node]


class TopLevelNode(Node):
    def __init__(
        self,
        encoding: 'concat.lex.Token',
        children: 'concat.astutils.WordsOrStatements',
    ):
        super().__init__()
        self.encoding = encoding.value
        self.location = encoding.start
        self.children: concat.astutils.WordsOrStatements = children

    def __repr__(self) -> str:
        return 'TopLevelNode(Token("ENCODING", {!r}, {!r}), {!r})'.format(
            self.encoding, self.location, self.children
        )


class StatementNode(Node, abc.ABC):
    pass


class ImportStatementNode(StatementNode):
    def __init__(
        self,
        module: str,
        asname: Optional[str] = None,
        location: 'Location' = (0, 0),
    ):
        super().__init__()
        self.location = location
        self.children = []
        self.value = module
        self.asname = asname

    def __str__(self) -> str:
        string = 'import {}'.format(self.value)
        if self.asname is not None:
            string += ' as {}'.format(self.asname)
        return string


class WordNode(Node, abc.ABC):
    pass


class CastWordNode(WordNode):
    def __init__(
        self, type: 'concat.typecheck.IndividualTypeNode', location: 'Location'
    ):
        super().__init__()
        self.location = location
        self.children = []
        self.type = type

    def __repr__(self) -> str:
        return '{}({!r}, {!r})'.format(
            type(self).__qualname__, self.type, self.location
        )


class PushWordNode(WordNode):
    def __init__(self, child: WordNode):
        super().__init__()
        self.location = child.location
        self.children: List[WordNode] = [child]

    def __str__(self) -> str:
        return '$' + str(self.children[0])

    def __repr__(self) -> str:
        return 'PushWordNode({!r})'.format(self.children[0])


class NumberWordNode(WordNode):
    def __init__(self, number: 'concat.lex.Token'):
        super().__init__()
        self.location = number.start
        self.children: List[Node] = []
        try:
            self.value = eval(number.value)
        except SyntaxError:
            raise ValueError(
                '{!r} cannot eval to a number'.format(number.value)
            )

    def __repr__(self) -> str:
        return 'NumberWordNode(Token("NUMBER", {!r}, {!r}))'.format(
            str(self.value), self.location
        )


class StringWordNode(WordNode):
    def __init__(self, string: 'concat.lex.Token') -> None:
        super().__init__()
        self.location = string.start
        self.children: List[Node] = []
        try:
            self.value = eval(string.value)
        except SyntaxError:
            raise ValueError(
                '{!r} cannot eval to a string'.format(string.value)
            )


class QuoteWordNode(WordNode):
    def __init__(
        self,
        children: Sequence[WordNode],
        location: Tuple[int, int],
        input_stack_type: Optional['TypeSequenceNode'] = None,
    ):
        super().__init__()
        self.location = location
        self.children: Sequence[WordNode] = children
        self.input_stack_type = input_stack_type

    def __str__(self) -> str:
        input_stack_type = (
            ''
            if self.input_stack_type is None
            else str(self.input_stack_type) + ': '
        )
        return '(' + input_stack_type + ' '.join(map(str, self.children)) + ')'


class NameWordNode(WordNode):
    def __init__(self, name: 'concat.lex.Token'):
        super().__init__()
        self.location = name.start
        self.children: List[Node] = []
        self.value = name.value

    def __str__(self) -> str:
        return self.value


class AttributeWordNode(WordNode):
    def __init__(self, attribute: 'concat.lex.Token'):
        super().__init__()
        self.location = attribute.start
        self.children: List[Node] = []
        self.value = attribute.value

    def __repr__(self) -> str:
        return 'AttributeWordNode(Token("NAME", {!r}, {!r}))'.format(
            self.value, self.location
        )


T = TypeVar('T')


class ParserDict(Dict[str, parsy.Parser]):
    def __init__(self) -> None:
        # These parsers act on lists of tokens.
        pass

    def extend_with(self: T, extension: Callable[[T], None]) -> None:
        extension(self)

    def parse(self, tokens: Sequence['concat.lex.Token']) -> TopLevelNode:
        return self['top-level'].parse(list(tokens))

    def token(self, typ: str) -> parsy.Parser:
        description = '{} token'.format(typ)
        return parsy.test_item(lambda token: token.type == typ, description)

    def ref_parser(self, name: str) -> parsy.Parser:
        @parsy.generate
        def parser():
            return (yield self[name])

        return parser


if TYPE_CHECKING:
    from concat.typecheck import StackEffectTypeNode


# Patches to parsy for better errors--useful for debugging


class ParseError(parsy.ParseError):
    def line_info(self):
        return '{}:{} ({!r} here)'.format(
            *self.stream[self.index].start, self.stream[self.index]
        )


# let's lie
parsy.ParseError = ParseError  # type: ignore


class BytesWordNode(WordNode):
    def __init__(self, bytes: 'concat.lex.Token'):
        super().__init__()
        self.children = []
        self.location = bytes.start
        self.value = eval(bytes.value)


class IterableWordNode(WordNode, abc.ABC):
    @abc.abstractmethod
    def __init__(self, element_words: Iterable['Words'], location: 'Location'):
        super().__init__()
        self.children = []
        self.location = location
        for children in element_words:
            self.children += list(children)
        self.element_words = element_words


class TupleWordNode(IterableWordNode):
    def __init__(self, element_words: Iterable['Words'], location: 'Location'):
        super().__init__(element_words, location)
        self.tuple_children = element_words


class ListWordNode(IterableWordNode):
    def __init__(self, element_words: Iterable['Words'], location: 'Location'):
        super().__init__(element_words, location)
        self.list_children = element_words


class FuncdefStatementNode(StatementNode):
    def __init__(
        self,
        name: 'Token',
        decorators: Iterable[WordNode],
        annotation: Optional[Iterable[WordNode]],
        body: 'WordsOrStatements',
        location: 'Location',
        stack_effect: Optional['StackEffectTypeNode'] = None,
    ):
        super().__init__()
        self.location = location
        self.name = name.value
        self.decorators = decorators
        self.annotation = annotation
        self.body = body
        self.children = [
            *self.decorators,
            *(self.annotation or []),
            *self.body,
        ]
        self.stack_effect = stack_effect

    def __repr__(self) -> str:
        return 'FuncdefStatementNode(decorators={!r}, name={!r}, annotation={!r}, body={!r}, stack_effect={!r}, location={!r})'.format(
            self.decorators,
            self.name,
            self.annotation,
            self.body,
            self.stack_effect,
            self.location,
        )


class AsyncFuncdefStatementNode(FuncdefStatementNode):
    pass


class FromImportStatementNode(ImportStatementNode):
    def __init__(
        self,
        relative_module: str,
        imported_name: str,
        asname: Optional[str] = None,
        location: 'Location' = (0, 0),
    ):
        super().__init__(relative_module, asname, location)
        self.imported_name = imported_name


class FromImportStarStatementNode(FromImportStatementNode):
    def __init__(self, module: str, location: 'Location' = (0, 0)):
        super().__init__(module, '*', None, location)


class ClassdefStatementNode(StatementNode):
    def __init__(
        self,
        name: str,
        body: 'WordsOrStatements',
        location: 'Location',
        decorators: Optional['Words'] = None,
        bases: Iterable['Words'] = (),
        keyword_args: Iterable[Tuple[str, WordNode]] = (),
    ):
        super().__init__()
        self.location = location
        self.children = body
        self.class_name = name
        self.decorators = [] if decorators is None else decorators
        self.bases = bases
        self.keyword_args = keyword_args


def extension(parsers: ParserDict) -> None:
    # This parses the top level of a file.
    # top level =
    #   ENCODING, (word | statement | NEWLINE)*, [ NEWLINE ],
    #   ENDMARKER ;
    @parsy.generate
    def top_level_parser() -> Generator[parsy.Parser, Any, TopLevelNode]:
        encoding = yield parsers.token('ENCODING')
        newline = parsers.token('NEWLINE')
        statement = parsers['statement']
        word = parsers['word']
        children = yield (word | statement | newline).many()
        children = [
            child
            for child in children
            if not isinstance(child, concat.lex.Token)
        ]
        yield parsers.token('ENDMARKER')
        return TopLevelNode(encoding, children)

    parsers['top-level'] = desc_cumulatively(top_level_parser, 'top level')

    # This parses one of many types of statement.
    # The specific statement node is returned.
    # statement = import statement ;
    parsers['statement'] = parsers.ref_parser('import-statement')

    ImportStatementParserGenerator = Generator[
        parsy.Parser, Any, ImportStatementNode
    ]

    # This parses one of many types of word.
    # The specific word node is returned.
    # word =
    #   push word | literal word | name word | attribute word | quote word ;
    # literal word = number word | string word ;
    parsers['word'] = parsy.alt(
        parsers.ref_parser('push-word'),
        parsers.ref_parser('quote-word'),
        parsers.ref_parser('literal-word'),
        parsers.ref_parser('name-word'),
        parsers.ref_parser('attribute-word'),
    )
    parsers['literal-word'] = parsers.ref_parser(
        'number-word'
    ) | parsers.ref_parser('string-word')

    parsers['name-word'] = parsers.token('NAME').map(NameWordNode)

    parsers['number-word'] = parsers.token('NUMBER').map(NumberWordNode)

    parsers['string-word'] = parsers.token('STRING').map(StringWordNode)

    # This parses a quotation.
    # quote word = LPAR, word*, RPAR ;
    @parsy.generate('quote word')
    def quote_word_parser() -> Generator[parsy.Parser, Any, QuoteWordNode]:
        lpar = yield parsers.token('LPAR')
        if 'type-sequence' in parsers:
            input_stack_type_parser = parsers[
                'type-sequence'
            ] << parsers.token('COLON')
            input_stack_type = yield input_stack_type_parser.optional()
        else:
            input_stack_type = None
        children = yield parsers['word'].many()
        yield parsers.token('RPAR')
        return QuoteWordNode(children, lpar.start, input_stack_type)

    parsers['quote-word'] = quote_word_parser

    # This parses a push word into a node.
    # push word = DOLLARSIGN, word ;
    word = parsers.ref_parser('word')
    dollarSign = parsers.token('DOLLARSIGN')
    parsers['push-word'] = dollarSign >> word.map(PushWordNode)

    # Parsers an attribute word.
    # attribute word = DOT, NAME ;
    dot = parsers.token('DOT')
    name = parsers.token('NAME')
    parsers['attribute-word'] = dot >> name.map(AttributeWordNode)

    parsers['literal-word'] |= parsy.alt(
        parsers.ref_parser('bytes-word'),
        parsers.ref_parser('tuple-word'),
        parsers.ref_parser('list-word'),
    )

    parsers['word'] |= parsy.alt(parsers.ref_parser('operator-word'),)

    parsers['operator-word'] = parsy.fail('operator')

    from concat.operators import operators

    for operator_name, token_type, node_type, _ in operators:
        parser_name = operator_name + '-word'
        parsers[parser_name] = parsers.token(token_type).map(node_type)
        parsers['operator-word'] |= parsers.ref_parser(parser_name)

    # This parses a bytes word.
    # bytes word = BYTES ;
    parsers['bytes-word'] = parsers.token('BYTES').map(BytesWordNode)

    def iterable_word_parser(
        delimiter: str, cls: Type[IterableWordNode], desc: str
    ) -> 'parsy.Parser[Token, IterableWordNode]':
        @parsy.generate
        def parser() -> Generator:
            location = (yield parsers.token('L' + delimiter)).start
            element_words = yield word_list_parser
            yield parsers.token('R' + delimiter)
            return cls(element_words, location)

        return concat.parser_combinators.desc_cumulatively(parser, desc)

    # This parses a tuple word.
    # tuple word = LPAR, word list, RPAR ;
    parsers['tuple-word'] = iterable_word_parser(
        'PAR', TupleWordNode, 'tuple word'
    )

    # This parses a list word.
    # list word = LSQB, word list, RSQB ;
    parsers['list-word'] = iterable_word_parser(
        'SQB', ListWordNode, 'list word'
    )

    # word list = (COMMA | word+, COMMA | word+, (COMMA, word+)+, [ COMMA ]) ;
    @parsy.generate('word list')
    def word_list_parser() -> Generator:
        empty: 'parsy.Parser[Token, List[Words]]' = parsers.token(
            'COMMA'
        ).result([])
        singleton = parsy.seq(
            parsers['word'].at_least(1) << parsers.token('COMMA')
        )
        multiple_element = (
            parsers['word'].at_least(1).sep_by(parsers.token('COMMA'), min=2)
            << parsers.token('COMMA').optional()
        )
        element_words = yield (multiple_element | singleton | empty)
        return element_words

    parsers['statement'] |= parsy.alt(
        parsers.ref_parser('async-funcdef-statement'),
        parsers.ref_parser('classdef-statement'),
        parsers.ref_parser('funcdef-statement'),
    )

    from concat.astutils import flatten

    parsers['target-words'] = (
        parsers.ref_parser('target-word').sep_by(parsers.token('COMMA'), min=1)
        << parsers.token('COMMA').optional()
    ).map(flatten)

    parsers['target-word'] = parsy.alt(
        parsers.ref_parser('name-word'),
        parsers.token('LPAR')
        >> parsers.ref_parser('target-words')
        << parsers.token('RPAR'),
        parsers.token('LSQB')
        >> parsers.ref_parser('target-words')
        << parsers.token('RSQB'),
        parsers.ref_parser('attribute-word'),
        parsers.ref_parser('subscription-word'),
        parsers.ref_parser('slice-word'),
    )

    # This parses an async function definition.
    # async funcdef statement = ASYNC, funcdef statement ;
    @parsy.generate('async funcdef statement')
    def async_funcdef_statement_parser() -> Generator:
        location = (yield parsers.token('ASYNC')).start
        func: FuncdefStatementNode = (yield parsers['funcdef-statement'])
        name = concat.lex.Token()
        name.value = func.name
        return AsyncFuncdefStatementNode(
            name,
            func.decorators,
            func.annotation,
            func.body,
            location,
            func.stack_effect,
        )

    parsers['async-funcdef-statement'] = async_funcdef_statement_parser

    # This parses a function definition.
    # funcdef statement = DEF, NAME, [ LPAR, stack effect, RPAR ], decorator*,
    #   [ annotation ], COLON, suite ;
    # decorator = AT, word ;
    # annotation = RARROW, word* ;
    # suite = NEWLINE, INDENT, (word | statement, NEWLINE)+, DEDENT | statement
    #    | word+ ;
    # The stack effect syntax is defined within the typecheck module.
    @parsy.generate
    def funcdef_statement_parser() -> Generator:
        location = (yield parsers.token('DEF')).start
        name = yield parsers.token('NAME')
        if (yield parsers.token('LPAR').optional()):
            effect_ast = yield parsers['stack-effect-type']
            yield parsers.token('RPAR')
        else:
            effect_ast = None
        decorators = yield decorator.many()
        annotation = yield annotation_parser.optional()
        yield parsers.token('COLON')
        body = yield suite
        return FuncdefStatementNode(
            name, decorators, annotation, body, location, effect_ast
        )

    parsers['funcdef-statement'] = concat.parser_combinators.desc_cumulatively(
        funcdef_statement_parser, 'funcdef statement'
    )

    decorator = parsers.token('AT') >> parsers.ref_parser('word')

    annotation_parser = (
        parsers.token('RARROW') >> parsers.ref_parser('word').many()
    )

    @parsy.generate
    def suite():
        words = parsers['word'].at_least(1)
        statement = parsy.seq(parsers['statement'])
        block_content = (
            parsers['word'] << parsers.token('NEWLINE').optional()
            | parsers['statement'] << parsers.token('NEWLINE')
        ).at_least(1)
        indented_block = (
            parsers.token('NEWLINE').optional()
            >> parsers.token('INDENT')
            >> block_content
            << parsers.token('DEDENT')
        )
        return (yield indented_block | statement | words)

    suite = concat.parser_combinators.desc_cumulatively(suite, 'suite')

    @parsy.generate('module')
    def module():
        name = parsers.token('NAME').map(operator.attrgetter('value'))
        return '.'.join((yield name.sep_by(parsers.token('DOT'), min=1)))

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
        # TODO: Support importing multiple names at once
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
            keyword_args,
        )

    parsers['classdef-statement'] = classdef_statement_parser

    bases = parsers.ref_parser('tuple-word').map(
        operator.attrgetter('tuple_children')
    )

    keyword_arg = parsy.seq(
        parsers.token('NAME').map(operator.attrgetter('value'))
        << parsers.token('EQUAL'),
        parsers.ref_parser('word'),
    )

    parsers['word'] |= parsers.ref_parser('cast-word')

    @parsy.generate
    def cast_word_parser() -> Generator:
        location = (yield parsers.token('CAST')).start
        yield parsers.token('LPAR')
        type_ast = yield parsers['type']
        yield parsers.token('RPAR')
        return CastWordNode(type_ast, location)

    # This parses a cast word.
    # none word = LPAR, type, RPAR, CAST ;
    # The grammar of 'type' is defined by the typechecker.
    parsers['cast-word'] = concat.parser_combinators.desc_cumulatively(
        cast_word_parser, 'cast word'
    )
