import concat.astutils
import concat.level1.typecheck
import concat.level2.parse
from typing import Tuple, Generator
import dataclasses
import abc
import parsy


@dataclasses.dataclass
class TypeNode(concat.level0.parse.Node, abc.ABC):
    location: concat.astutils.Location


@dataclasses.dataclass
class AttributeTypeNode(TypeNode):
    name: str
    type: TypeNode


@dataclasses.dataclass
class NamedTypeNode(TypeNode):
    name: str


def infer(env: concat.level1.typecheck.Environment, program: concat.astutils.WordsOrStatements) -> Tuple[concat.level1.typecheck.Substitutions, concat.level1.typecheck.StackEffect]:
    if isinstance(program[-1], concat.level2.parse.CastWordNode):
        subs, (input, output) = concat.level1.typecheck.infer(env, program[:-1])
        new_type = ast_to_type(program[-1].type, subs, env)
        rest = concat.level1.typecheck.drop_last_from_type_seq(output)
        return subs, concat.level1.typecheck.StackEffect(input, [*rest, new_type])
    else:
        raise NotImplementedError


def ast_to_type(ast: TypeNode, subs: concat.level1.typecheck.Substitutions, env: concat.level1.typecheck.Environment) -> concat.level1.typecheck.Type:
    if isinstance(ast, AttributeTypeNode):
        attr_type = ast_to_type(ast.type, subs, env)
        return concat.level1.typecheck.TypeWithAttribute(ast.name, attr_type)
    elif isinstance(ast, NamedTypeNode):
        # FIXME: We should look in the environment.
        return getattr(concat.level1.typecheck.PrimitiveTypes, ast.name)
    else:
        raise NotImplementedError(ast)


# Parsing type annotations


def typecheck_extension(parsers: concat.level0.parse.ParserDict) -> None:
    @parsy.generate
    def attribute_type_parser() -> Generator:
        location = (yield parsers.token('DOT')).start
        name = (yield parsers.token('NAME')).value
        yield parsers.token('COLON')
        type = yield parsers['type']
        return AttributeTypeNode(location, name, type)

    @parsy.generate
    def named_type_parser() -> Generator:
        name_token = yield parsers.token('NAME')
        return NamedTypeNode(name_token.start, name_token.value)

    parsers['type'] = parsy.alt(
        concat.parser_combinators.desc_cumulatively(
            attribute_type_parser, 'attribute type'),
        concat.parser_combinators.desc_cumulatively(
            named_type_parser, 'named type')
    )