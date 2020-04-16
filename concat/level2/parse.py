"""The level two Concat parser.

This parser is designed to extend the level one parser.
"""
import concat.level0.parse
import concat.level2.typecheck
from concat.astutils import Location
import concat.parser_combinators
from typing import Generator
import parsy


class CastWordNode(concat.level0.parse.WordNode):
    def __init__(self, type: concat.level2.typecheck.TypeNode, location: Location):
        super().__init__()
        self.location = location
        self.children = []
        self.type = type


def level_2_extension(parsers: concat.level0.parse.ParserDict) -> None:
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
        cast_word_parser, 'cast word')
