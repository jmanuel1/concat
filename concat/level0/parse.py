"""The level zero Concat parser.

On Extensibility:

The parser uses parsy, a parser combinator library. A custom parser
primitive is used to call the lexer.

- The extension mechanism:
Assume there is a level 0 word parser. In level 1:

# import * level 0 parser module

def word_ext(parsers):
    parsers['word'] |= extensionParser

extendedParsers = level0Parsers.extend_with(word_ext)

The parsers object is a dictionary with a few methods:
extend_with(extension) -- returns a new object that adds the extension

- Other possible approaches:
Hand-written recursive descent parser that tries extensions when throwing an
exception: I would have to implement indefinte backtracking myself to have
well-defined extension points. Libraries like pyparsing would do that for me.

parsy is used instead of pyparsing since it supports having a separate
tokenization phase.
"""
import abc
from typing import (Iterable, TypeVar, Any, Sequence, Tuple,
                    Dict, Generator, List, Callable)
import concat.level0.lex
import concat.astutils
from concat.parser_combinators import desc_cumulatively
import parsy


class Node(abc.ABC):

    def __init__(self):
        self.location = (0, 0)
        self.children: Iterable[Node]


class TopLevelNode(Node):

    def __init__(
        self,
        encoding: 'concat.level0.lex.Token',
        children: 'concat.astutils.WordsOrStatements'
    ):
        super().__init__()
        self.encoding = encoding.value
        self.location = encoding.start
        self.children: concat.astutils.WordsOrStatements = children


class StatementNode(Node, abc.ABC):
    pass


class ImportStatementNode(StatementNode):

    def __init__(
        self,
        module: 'concat.level0.lex.Token',
        location: Tuple[int, int]
    ):
        super().__init__()
        self.location = location
        self.children = []
        self.value = module.value


class WordNode(Node):
    pass


class PushWordNode(WordNode):

    def __init__(self, child: WordNode):
        super().__init__()
        self.location = child.location
        self.children: List[WordNode] = [child]


class NumberWordNode(WordNode):

    def __init__(self, number: 'concat.level0.lex.Token'):
        super().__init__()
        self.location = number.start
        self.children: List[Node] = []
        self.value = eval(number.value)


class StringWordNode(WordNode):

    def __init__(self, string: 'concat.level0.lex.Token') -> None:
        super().__init__()
        self.location = string.start
        self.children: List[Node] = []
        self.value = eval(string.value)


class QuoteWordNode(WordNode):

    def __init__(
        self,
        children: Sequence[WordNode],
        location: Tuple[int, int]
    ):
        super().__init__()
        self.location = location
        self.children: Sequence[WordNode] = children


class NameWordNode(WordNode):

    def __init__(self, name: 'concat.level0.lex.Token'):
        super().__init__()
        self.location = name.start
        self.children: List[Node] = []
        self.value = name.value


class AttributeWordNode(WordNode):

    def __init__(self, attribute: 'concat.level0.lex.Token'):
        super().__init__()
        self.location = attribute.start
        self.children: List[Node] = []
        self.value = attribute.value


T = TypeVar('T')


class ParserDict(Dict[str, parsy.Parser]):

    def __init__(self) -> None:
        # These parsers act on lists of tokens.
        pass

    def extend_with(self: T, extension: Callable[[T], None]) -> None:
        extension(self)

    def parse(
        self,
        tokens: Sequence['concat.level0.lex.Token']
    ) -> TopLevelNode:
        return self['top-level'].parse(list(tokens))

    def token(self, typ: str) -> parsy.Parser:
        description = '{} token'.format(typ)
        return parsy.test_item(lambda token: token.type == typ, description)

    def ref_parser(self, name: str) -> parsy.Parser:
        @parsy.generate
        def parser():
            return (yield self[name])
        return parser


def level_0_extension(parsers: ParserDict) -> None:
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
            child for child in children
            if not isinstance(child, concat.level0.lex.Token)]
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

    # Parses a simple import statement.
    # import statement = IMPORT, NAME
    @parsy.generate('import statement')
    def import_statement_parser() -> ImportStatementParserGenerator:
        keyword = yield parsers.token('IMPORT')
        name = yield parsers.token('NAME')
        return ImportStatementNode(name, keyword.start)

    parsers['import-statement'] = import_statement_parser

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
        parsers.ref_parser('attribute-word')
    )
    parsers['literal-word'] = parsers.ref_parser(
        'number-word') | parsers.ref_parser('string-word')

    parsers['name-word'] = parsers.token('NAME').map(NameWordNode)

    parsers['number-word'] = parsers.token('NUMBER').map(NumberWordNode)

    parsers['string-word'] = parsers.token('STRING').map(StringWordNode)

    # This parses a quotation.
    # quote word = LPAR, word*, RPAR ;
    @parsy.generate('quote word')
    def quote_word_parser() -> Generator[parsy.Parser, Any, QuoteWordNode]:
        lpar = yield parsers.token('LPAR')
        children = yield parsers.ref_parser('word').many()
        yield parsers.token('RPAR')
        return QuoteWordNode(children, lpar.start)

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
