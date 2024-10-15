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
"""
from __future__ import annotations
import abc
import ast
import operator
from typing import (
    Any,
    Generator,
    Iterable,
    Iterator,
    List,
    Optional,
    Sequence,
    TYPE_CHECKING,
    Tuple,
    Type,
    TypeVar,
    Union,
)
import concat.lex
import concat.astutils
import concat.parser_combinators
from concat.parser_combinators.recovery import bracketed, recover, skip_until
from concat.parser_dict import ParserDict

if TYPE_CHECKING:
    from concat.lex import Token
    from concat.typecheck import TypeSequenceNode
    from concat.astutils import Location, Words, WordsOrStatements


class Node(abc.ABC):
    def __init__(
        self,
        location: Location,
        end_location: Location,
        children: Iterable[Node],
    ):
        self.location = location
        self.end_location = end_location
        self.children = list(children)
        assert location[0] <= end_location[0]
        assert location[0] != end_location[0] or location[1] <= end_location[1]

    def assert_no_parse_errors(self) -> None:
        failures = list(self.parsing_failures)
        if failures:
            raise concat.parser_combinators.ParseError(failures)

    @property
    def parsing_failures(
        self,
    ) -> Iterator[concat.parser_combinators.FailureTree]:
        for child in self.children:
            yield from child.parsing_failures


class TopLevelNode(Node):
    def __init__(
        self,
        encoding: 'concat.lex.Token',
        children: 'concat.astutils.WordsOrStatements',
    ):
        end_location = children[-1].end_location if children else encoding.end
        super().__init__(encoding.start, end_location, children)
        self.encoding = encoding.value
        self._encoding_token = encoding

    def __repr__(self) -> str:
        return f'TopLevelNode({self._encoding_token!r}, {self.children!r})'


class StatementNode(Node, abc.ABC):
    pass


class ImportStatementNode(StatementNode):
    def __init__(
        self,
        module: str,
        location: 'Location',
        end_location: Location,
        asname: Optional[str] = None,
    ):
        super().__init__(location, end_location, [])
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
        super().__init__(location, type.end_location, [type])
        self.type = type

    def __repr__(self) -> str:
        return '{}({!r}, {!r})'.format(
            type(self).__qualname__, self.type, self.location
        )


class FreezeWordNode(WordNode):
    """The AST type for freeze words.

    Freeze words prevent a polymorphic term's type from being instantiated.
    """

    def __init__(self, location: 'Location', word: WordNode) -> None:
        super().__init__(location, word.end_location, [word])
        self.word = word

    def __str__(self) -> str:
        return f':~{self.word}'

    def __repr__(self) -> str:
        return f'{type(self).__qualname__}({self.location!r}, {self.word!r})'


class PushWordNode(WordNode):
    def __init__(self, location: Location, child: WordNode):
        super().__init__(location, child.end_location, [child])

    def __str__(self) -> str:
        return '$' + str(self.children[0])

    def __repr__(self) -> str:
        return f'PushWordNode({self.location!r}, {self.children[0]!r})'


class NumberWordNode(WordNode):
    def __init__(self, number: 'concat.lex.Token'):
        super().__init__(number.start, number.end, [])
        try:
            self.value = ast.literal_eval(number.value)
        except SyntaxError:
            raise ValueError(
                '{!r} cannot eval to a number'.format(number.value)
            )

    def __repr__(self) -> str:
        return f'NumberWordNode(Token("NUMBER", {str(self.value)!r}, {self.location!r}, {self.end_location!r}))'


class StringWordNode(WordNode):
    def __init__(self, string: 'concat.lex.Token') -> None:
        super().__init__(string.start, string.end, [])
        try:
            self.value = ast.literal_eval(string.value)
        except SyntaxError:
            raise ValueError(
                '{!r} cannot eval to a string'.format(string.value)
            )


class QuoteWordNode(WordNode):
    def __init__(
        self,
        children: Sequence[WordNode],
        location: Location,
        end_location: Location,
        input_stack_type: Optional['TypeSequenceNode'] = None,
    ):
        super().__init__(location, end_location, children)
        self.input_stack_type = input_stack_type

    def __str__(self) -> str:
        input_stack_type = (
            ''
            if self.input_stack_type is None
            else str(self.input_stack_type) + ': '
        )
        return '(' + input_stack_type + ' '.join(map(str, self.children)) + ')'

    def __repr__(self) -> str:
        return f'QuoteWordNode(children={self.children!r}, location={self.location!r}, end_location={self.end_location!r}, input_stack_type={self.input_stack_type!r})'


class NameWordNode(WordNode):
    def __init__(self, name: 'concat.lex.Token'):
        super().__init__(name.start, name.end, [])
        self.value = name.value

    def __str__(self) -> str:
        return self.value


class AttributeWordNode(WordNode):
    def __init__(self, location: Location, attribute: 'concat.lex.Token'):
        super().__init__(location, attribute.end, [])
        self.value = attribute.value
        self._name_token = attribute

    def __repr__(self) -> str:
        return f'AttributeWordNode({self.location!r}, {self._name_token!r})'


T = TypeVar('T')


if TYPE_CHECKING:
    from concat.typecheck import StackEffectTypeNode


class ParseError(Node):
    """AST node for a parsing error that was recovered from."""

    def __init__(self, result: concat.parser_combinators.Result) -> None:
        # TODO: Set location
        super().__init__((0, 0), (0, 0), [])
        self.result = result

    @property
    def parsing_failures(
        self,
    ) -> Iterator[concat.parser_combinators.FailureTree]:
        assert self.result.failures is not None
        yield self.result.failures

    def __repr__(self) -> str:
        return f'{type(self).__qualname__}(result={self.result!r})'


class BytesWordNode(WordNode):
    def __init__(self, bytes: 'concat.lex.Token'):
        super().__init__(bytes.start, bytes.end, [])
        self.value = ast.literal_eval(bytes.value)


class IterableWordNode(WordNode, abc.ABC):
    @abc.abstractmethod
    def __init__(
        self,
        element_words: Iterable['Words'],
        location: 'Location',
        end_location: 'Location',
    ):
        flattened_children = []
        for children in element_words:
            flattened_children += list(children)
        super().__init__(location, end_location, flattened_children)
        self.element_words = list(element_words)

    def __repr__(self) -> str:
        return f'{type(self).__qualname__}(element_words={self.element_words!r}, location={self.location!r}, end_location={self.end_location!r})'


class TupleWordNode(IterableWordNode):
    def __init__(
        self,
        element_words: Iterable['Words'],
        location: 'Location',
        end_location: 'Location',
    ):
        super().__init__(element_words, location, end_location)
        self.tuple_children = element_words


class ListWordNode(IterableWordNode):
    def __init__(
        self,
        element_words: Iterable['Words'],
        location: 'Location',
        end_location: 'Location',
    ):
        super().__init__(element_words, location, end_location)
        self.list_children = element_words


class FuncdefStatementNode(StatementNode):
    def __init__(
        self,
        name: 'Token',
        type_parameters: Sequence[Tuple['Token', Node]],
        decorators: Iterable[WordNode],
        annotation: Optional[Iterable[WordNode]],
        body: 'WordsOrStatements',
        location: 'Location',
        stack_effect: 'StackEffectTypeNode',
    ):
        children = [
            *map(lambda p: p[1], type_parameters),
            *decorators,
            *(annotation or []),
            stack_effect,
            *body,
        ]
        super().__init__(location, body[-1].end_location, children)
        self.location = location
        self.name = name.value
        self.type_parameters = type_parameters
        self.decorators = decorators
        self.annotation = annotation
        self.body = body
        self.stack_effect = stack_effect

    def __repr__(self) -> str:
        return f'FuncdefStatementNode(decorators={self.decorators!r}, name={self.name!r}, type_parameters={self.type_parameters!r}, annotation={self.annotation!r}, body={self.body!r}, stack_effect={self.stack_effect!r}, location={self.location!r})'


class FromImportStatementNode(ImportStatementNode):
    def __init__(
        self,
        relative_module: str,
        imported_name: str,
        location: 'Location',
        end_location: Location,
        asname: Optional[str] = None,
    ):
        super().__init__(relative_module, location, end_location, asname)
        self.imported_name = imported_name


class FromImportStarStatementNode(FromImportStatementNode):
    def __init__(
        self, module: str, location: 'Location', end_location: Location
    ):
        super().__init__(module, '*', location, end_location, None)


class ClassdefStatementNode(StatementNode):
    def __init__(
        self,
        name: str,
        body: 'WordsOrStatements',
        location: 'Location',
        decorators: 'Words',
        bases: Iterable['Words'] = (),
        keyword_args: Iterable[Tuple[str, WordNode]] = (),
        type_parameters: Iterable[Node] = (),
        is_variadic: bool = False,
    ):
        children = list(*bases)
        children.extend(type_parameters)
        children.extend(map(lambda x: x[1], keyword_args))
        children.extend(decorators)
        children.extend(body)
        super().__init__(location, body[-1].end_location, children)
        self.class_name = name
        self.decorators = [] if decorators is None else decorators
        self.bases = bases
        self.keyword_args = keyword_args
        self.type_parameters = type_parameters
        self.is_variadic = is_variadic
        self.body = body


class PragmaNode(Node):
    def __init__(
        self,
        location: 'Location',
        end_location: Location,
        pragma_name: str,
        args: Sequence[str],
    ) -> None:
        super().__init__(location, end_location, [])
        self.pragma = pragma_name
        self.args = args


def token(typ: str) -> concat.parser_combinators.Parser:
    description = f'{typ} token'
    return concat.parser_combinators.test_item(
        lambda token: token.type == typ, description
    )


def extension(parsers: ParserDict) -> None:
    # This parses the top level of a file.
    # top level =
    #   ENCODING, (word | statement | NEWLINE)*, [ NEWLINE ],
    #   ENDMARKER ;
    @concat.parser_combinators.generate
    def top_level_parser() -> Generator[
        concat.parser_combinators.Parser, Any, TopLevelNode
    ]:
        encoding = yield token('ENCODING')
        newline = token('NEWLINE')
        statement = parsers['statement']
        word = parsers['word']
        children = yield (word | statement | newline).commit().many()
        children = [
            child
            for child in children
            if not isinstance(child, concat.lex.Token)
        ]
        end_marker = yield recover(
            token('ENDMARKER'), skip_until(token('ENDMARKER'))
        )
        if isinstance(end_marker, tuple):
            children.append(ParseError(end_marker[1]))
            yield token('ENDMARKER')

        return TopLevelNode(encoding, children)

    parsers['top-level'] = top_level_parser.desc('top level')

    # This parses one of many types of statement.
    # The specific statement node is returned.
    # statement = import statement ;
    parsers['statement'] = parsers.ref_parser('import-statement')

    # This parses one of many types of word.
    # The specific word node is returned.
    # word =
    #   push word | literal word | name word | attribute word | quote word ;
    # literal word = number word | string word ;
    parsers['word'] = concat.parser_combinators.alt(
        parsers.ref_parser('push-word'),
        parsers.ref_parser('quote-word'),
        parsers.ref_parser('literal-word'),
        parsers.ref_parser('name-word'),
        parsers.ref_parser('attribute-word'),
    )
    parsers['literal-word'] = parsers.ref_parser(
        'number-word'
    ) | parsers.ref_parser('string-word')

    parsers['name-word'] = token('NAME').map(NameWordNode)

    parsers['number-word'] = token('NUMBER').map(NumberWordNode)

    parsers['string-word'] = token('STRING').map(StringWordNode)

    @concat.parser_combinators.generate
    def quote_word_contents() -> Generator:
        if 'stack-effect-type-sequence' in parsers:
            input_stack_type_parser = parsers[
                'stack-effect-type-sequence'
            ] << token('COLON')
            input_stack_type = yield input_stack_type_parser.optional()
        else:
            input_stack_type = None
        children = yield parsers['word'].many()
        return {'children': children, 'input-stack-type': input_stack_type}

    # This parses a quotation.
    # quote word = LPAR, word*, RPAR ;
    @concat.parser_combinators.generate('quote word')
    def quote_word_parser() -> Generator[
        concat.parser_combinators.Parser, Any, QuoteWordNode
    ]:
        lpar = yield token('LPAR')
        input_stack_type = None
        children = yield recover(
            quote_word_contents, skip_until(token('RPAR'))
        )
        if isinstance(children, tuple):
            children = [children[1]]
        else:
            input_stack_type = children['input-stack-type']
            children = children['children']
        rpar = yield token('RPAR')
        return QuoteWordNode(children, lpar.start, rpar.end, input_stack_type)

    parsers['quote-word'] = quote_word_parser

    # This parses a push word into a node.
    # push word = DOLLARSIGN, (word | freeze word) ;
    # TODO: raise a parse error 'Cannot apply a word of polymorphic type. Maybe
    # try pushing the function and applying `call` to it?' for freeze words
    # outside a push.
    word = parsers.ref_parser('word')
    dollarSign = token('DOLLARSIGN')
    parsers['push-word'] = concat.parser_combinators.seq(
        dollarSign, parsers.ref_parser('freeze-word') | word
    ).map(lambda xs: PushWordNode(xs[0].start, xs[1]))

    # Parsers an attribute word.
    # attribute word = DOT, NAME ;
    dot = token('DOT')
    name = token('NAME')
    parsers['attribute-word'] = concat.parser_combinators.seq(dot, name).map(
        lambda xs: AttributeWordNode(xs[0].start, xs[1])
    )

    parsers['literal-word'] |= concat.parser_combinators.alt(
        parsers.ref_parser('bytes-word'),
        parsers.ref_parser('tuple-word'),
        parsers.ref_parser('list-word'),
    )

    # This parses a bytes word.
    # bytes word = BYTES ;
    parsers['bytes-word'] = token('BYTES').map(BytesWordNode)

    def iterable_word_parser(
        delimiter: str, cls: Type[IterableWordNode], desc: str
    ) -> 'concat.parser_combinators.Parser[Token, IterableWordNode]':
        @concat.parser_combinators.generate
        def parser() -> Generator:
            location = (yield token('L' + delimiter)).start
            element_words = yield word_list_parser
            end_location = (yield token('R' + delimiter)).end
            return cls(element_words, location, end_location)

        return parser.desc(desc)

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
    @concat.parser_combinators.generate('word list')
    def word_list_parser() -> Generator:
        empty: 'concat.parser_combinators.Parser[Token, List[Words]]' = token(
            'COMMA'
        ).result([])
        singleton = (parsers['word'].at_least(1) << token('COMMA')).map(
            lambda words: [words]
        )
        multiple_element = (
            parsers['word'].at_least(1).sep_by(token('COMMA'), min=2)
            << token('COMMA').optional()
        )
        element_words = yield (multiple_element | singleton | empty)
        return element_words

    parsers['statement'] |= concat.parser_combinators.alt(
        parsers.ref_parser('classdef-statement'),
        parsers.ref_parser('funcdef-statement'),
    )

    from concat.astutils import flatten

    parsers['target-words'] = (
        parsers.ref_parser('target-word').sep_by(token('COMMA'), min=1)
        << token('COMMA').optional()
    ).map(flatten)

    parsers['target-word'] = concat.parser_combinators.alt(
        parsers.ref_parser('name-word'),
        token('LPAR') >> parsers.ref_parser('target-words') << token('RPAR'),
        token('LSQB') >> parsers.ref_parser('target-words') << token('RSQB'),
        parsers.ref_parser('attribute-word'),
        parsers.ref_parser('subscription-word'),
        parsers.ref_parser('slice-word'),
    )

    # This parses a function definition.
    # funcdef statement = DEF, NAME, [ type parameters ], stack effect, decorator*,
    #   [ annotation ], COLON, suite ;
    # decorator = AT, word ;
    # annotation = RARROW, word* ;
    # suite = NEWLINE, INDENT, (word | statement, NEWLINE)+, DEDENT | statement
    #    | word+ ;
    # type parameters = "[", [ type parameter ],
    #   (",", type parameter)*, [ "," ], "]" ;
    # type parameter = NAME, COLON, type ;
    # The stack effect syntax is defined within the typecheck module.
    @concat.parser_combinators.generate
    def funcdef_statement_parser() -> Generator:
        location = (yield token('DEF')).start
        name = yield token('NAME')
        type_params = (yield type_parameters.optional()) or []
        effect_ast = yield parsers['stack-effect-type']
        decorators = yield decorator.many()
        annotation = yield annotation_parser.optional()
        yield token('COLON')
        body = yield suite
        return FuncdefStatementNode(
            name,
            type_params,
            decorators,
            annotation,
            body,
            location,
            effect_ast,
        )

    @concat.parser_combinators.generate
    def type_parameter() -> Generator:
        name = yield token('NAME')
        yield token('COLON')
        ty = yield parsers['type']
        return (name, ty)

    type_parameters = bracketed(
        token('LSQB'),
        type_parameter.sep_by(token('COMMA')) << token('COMMA').optional(),
        token('RQSB'),
    ).map(handle_recovery)

    parsers['funcdef-statement'] = funcdef_statement_parser.desc(
        'funcdef statement'
    )

    decorator = token('NAME').bind(
        lambda token: concat.parser_combinators.success(token)
        if token.value == '@'
        else concat.parser_combinators.fail('at sign (@)')
    ) >> parsers.ref_parser('word')

    annotation_parser = token('RARROW') >> parsers.ref_parser('word').many()

    @concat.parser_combinators.generate
    def suite():
        words = parsers['word'].at_least(1)
        statement = concat.parser_combinators.seq(parsers['statement'])
        block_content = (
            parsers['word'] << token('NEWLINE').optional()
            | parsers['statement'] << token('NEWLINE').optional()
        ).at_least(1)
        indented_block = token('NEWLINE').optional() >> bracketed(
            token('INDENT'), block_content, token('DEDENT')
        ).map(lambda x: [ParseError(x[1])] if isinstance(x, tuple) else x)
        return (yield indented_block | statement | words)

    suite = suite.desc('suite')

    @concat.parser_combinators.generate('module')
    def module():
        name = token('NAME').map(operator.attrgetter('value'))
        return '.'.join((yield name.sep_by(token('DOT'), min=1)))

    # These following parsers parse import statements.
    # import statement = IMPORT, module, [ AS, NAME ]
    #   | FROM, relative module, IMPORT, NAME, [ AS, NAME ]
    #   | FROM, module, IMPORT, STAR;
    # module = NAME, (DOT, NAME)* ;
    # relative module = DOT*, module | DOT+ ;

    @concat.parser_combinators.generate('import statement')
    def import_statement_parser() -> Generator:
        location = (yield token('IMPORT')).start
        module_name = yield module
        asname_parser = token('NAME').map(operator.attrgetter('value'))
        asname = None
        if (yield token('AS').optional()):
            asname = yield asname_parser
        return ImportStatementNode(module_name, asname, location)

    parsers['import-statement'] = import_statement_parser

    @concat.parser_combinators.generate('relative module')
    def relative_module():
        dot = token('DOT').map(operator.attrgetter('value'))
        return (yield (dot.many().concat() + module) | dot.at_least(1))

    @concat.parser_combinators.generate('from-import statement')
    def from_import_statement_parser() -> Generator:
        location = (yield token('FROM')).start
        module = yield relative_module
        name_parser = token('NAME').map(operator.attrgetter('value'))
        # TODO: Support importing multiple names at once
        imported_name = yield token('IMPORT') >> name_parser
        asname = None
        if (yield token('AS').optional()):
            asname = yield name_parser
        end_location = (yield concat.parser_combinators.peek_prev).end
        return FromImportStatementNode(
            module, imported_name, location, end_location, asname
        )

    parsers['import-statement'] |= from_import_statement_parser

    @concat.parser_combinators.generate('from-import-star statement')
    def from_import_star_statement_parser() -> Generator:
        location = (yield token('FROM')).start
        module_name = yield module
        yield token('IMPORT')
        end_location = (yield token('STAR')).end
        return FromImportStarStatementNode(module_name, location, end_location)

    parsers['import-statement'] |= from_import_star_statement_parser

    @concat.parser_combinators.generate('classdef statement')
    def classdef_statement_parser():
        """This parses a class definition statement.

        classdef statement = CLASS, NAME,
            [ LSQB, ((type variable, (COMMA, type variable)*, [ COMMA ]) | (type variable, NAME=...)), RSQB) ],
            decorator*, [ bases ], keyword arg*,
            COLON, suite ;
        bases = tuple word ;
        keyword arg = NAME, EQUAL, word ;"""
        location = (yield token('CLASS')).start
        name_token = yield token('NAME')
        is_variadic = False

        def ellispis_verify(
            tok: concat.lex.Token,
        ) -> concat.parser_combinators.Parser[concat.lex.Token, Any]:
            nonlocal is_variadic

            if tok.value == '...':
                is_variadic = True
                return concat.parser_combinators.success(None)
            return concat.parser_combinators.fail('a literal ellispis (...)')

        ellispis_parser = token('NAME').bind(ellispis_verify)
        type_parameters = (
            yield bracketed(
                token('LSQB'),
                (
                    concat.parser_combinators.seq(parsers['type-variable'])
                    << ellispis_parser
                )
                | (
                    parsers['type-variable'].sep_by(token('COMMA'))
                    << token('COMMA').optional()
                ),
                token('RSQB'),
            )
            .map(handle_recovery)
            .optional()
        )
        decorators = yield decorator.many()
        bases_list = yield bases.optional()
        keyword_args = yield keyword_arg.map(tuple).many()
        yield token('COLON')
        body = yield suite
        return ClassdefStatementNode(
            name_token.value,
            body,
            location,
            decorators,
            bases_list or [],
            keyword_args,
            type_parameters=type_parameters or [],
            is_variadic=is_variadic,
        )

    parsers['classdef-statement'] = classdef_statement_parser

    bases = parsers.ref_parser('tuple-word').map(
        operator.attrgetter('tuple_children')
    )

    keyword_arg = concat.parser_combinators.seq(
        token('NAME').map(operator.attrgetter('value')) << token('EQUAL'),
        parsers.ref_parser('word'),
    )

    @concat.parser_combinators.generate('internal pragma')
    def pragma_parser() -> Generator:
        """This parses a pragma for internal use.

        pragma = EXCLAMATIONMARK, @, @, qualified name+
        qualified name = module"""
        location = (yield token('EXCLAMATIONMARK')).start
        for _ in range(2):
            name_token = yield token('NAME')
            if name_token.value != '@':
                return concat.parser_combinators.fail('a literal at sign (@)')
        pragma_name = yield module
        args = yield module.many()
        end_location = (yield concat.parser_combinators.peek_prev).end
        return PragmaNode(location, end_location, pragma_name, args)

    parsers['pragma'] = pragma_parser
    parsers['statement'] |= parsers.ref_parser('pragma')

    parsers['word'] |= parsers.ref_parser('cast-word')

    @concat.parser_combinators.generate
    def cast_word_parser() -> Generator:
        location = (yield token('CAST')).start
        yield token('LPAR')
        type_ast = yield parsers['type']
        yield token('RPAR')
        return CastWordNode(type_ast, location)

    # This parses a cast word.
    # none word = LPAR, type, RPAR, CAST ;
    # The grammar of 'type' is defined by the typechecker.
    parsers['cast-word'] = cast_word_parser.desc('cast word')

    @concat.parser_combinators.generate
    def tilde_parser() -> Generator:
        name = yield token('NAME')
        if name.value != '~':
            yield concat.parser_combinators.fail('a tilde (~)')
        return name

    @concat.parser_combinators.generate
    def freeze_word_parser() -> Generator:
        location = (yield token('COLON')).start
        yield tilde_parser
        word = yield parsers['name-word'] | parsers['attribute-word']
        return FreezeWordNode(location, word)

    # This parses a freeze word.
    # freeze word = COLON, TILDE, (name word | attr word) ;
    # The freeze word prevents instantiation of type variables in the word that
    # follows it. Inspiration: https://arxiv.org/pdf/2004.00396.pdf ("FreezeML:
    # Complete and Easy Type Inference for First-Class Polymorphism")
    parsers['freeze-word'] = freeze_word_parser.desc('freeze word')

    # TODO: Have an error message for called freeze words in particular. This
    # causes the parser to loop.
    # parsers['word'] |= parsers['freeze-word'].should_fail(
    #     'not a freeze word, which has polymorphic type'
    # )


def handle_recovery(
    x: Union[
        Sequence[Node], Tuple[Any, concat.parser_combinators.Result[Any]],
    ]
) -> Sequence[Node]:
    if (
        isinstance(x, tuple)
        and len(x) > 1
        and isinstance(x[1], concat.parser_combinators.Result)
    ):
        return [ParseError(x[1])]
    return x
