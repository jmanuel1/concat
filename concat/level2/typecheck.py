import concat.astutils
import concat.level0.lex
import concat.level0.parse
import concat.level1.typecheck
import concat.level1.parse
import concat.level2.parse
from typing import Tuple, Generator, Sequence, Optional, Union, overload, cast
from typing_extensions import Literal
import dataclasses
import abc
import importlib
import parsy


@dataclasses.dataclass
class TypeNode(concat.level0.parse.Node, abc.ABC):
    location: concat.astutils.Location


class IndividualTypeNode(TypeNode, abc.ABC):
    @abc.abstractmethod
    def __init__(self, location: concat.astutils.Location) -> None:
        super().__init__(location)


# A dataclass is not used here because making this a subclass of an abstract
# class does not work without overriding __init__ even when it's a dataclass.
class AttributeTypeNode(IndividualTypeNode):
    def __init__(self, location: concat.astutils.Location, name: str, type: IndividualTypeNode) -> None:
        super().__init__(location)
        self.name = name
        self.type = type


class NamedTypeNode(IndividualTypeNode):
    def __init__(self, location: concat.astutils.Location, name: str) -> None:
        super().__init__(location)
        self.name = name

    def __repr__(self) -> str:
        return '{}({!r}, {!r})'.format(type(self).__qualname__, self.location, self.name)


class StackEffectTypeNode(IndividualTypeNode):
    def __init__(self, location: concat.astutils.Location, in_seq_var: Optional[concat.level0.lex.Token], input: Sequence[Tuple[concat.level0.lex.Token, IndividualTypeNode]], out_seq_var: Optional[concat.level0.lex.Token], output: Sequence[Tuple[concat.level0.lex.Token, IndividualTypeNode]]) -> None:
        super().__init__(location)
        self.input_sequence_variable = in_seq_var.value if in_seq_var else None

        def extract_value(i):
            return (i[0].value, i[1])
        self.input = [extract_value(i) for i in input]
        self.output_sequence_variable = out_seq_var.value if out_seq_var else None
        self.output = [extract_value(o) for o in output]

    def __repr__(self) -> str:
        return '{}({!r}, {!r}, {!r}, {!r}, location={!r})'.format(
            type(self).__qualname__,
            self.input_sequence_variable,
            self.input,
            self.output_sequence_variable,
            self.output,
            self.location,
        )


class IntersectionTypeNode(IndividualTypeNode):
    def __init__(self, location: concat.astutils.Location, type_1: IndividualTypeNode, type_2: IndividualTypeNode):
        super().__init__(location)
        self.type_1 = type_1
        self.type_2 = type_2


class PrimitiveInterfaces:
    subscriptable = concat.level1.typecheck.TypeWithAttribute(
        '__getitem__',
        concat.level1.typecheck.PrimitiveTypes.py_function,
    )

    subtractable = concat.level1.typecheck.PrimitiveInterface('subtractable')
    concat.level1.typecheck.PrimitiveTypes.int.add_supertype(subtractable)


class _NoReturnType(concat.level1.typecheck.PrimitiveType):
    def __init__(self) -> None:
        super().__init__('NoReturn')

    def is_subtype_of(self, _: concat.level1.typecheck.Type) -> Literal[True]:
        return True


class PrimitiveTypes:
    none = concat.level1.typecheck.PrimitiveType('None')
    ellipsis = concat.level1.typecheck.PrimitiveType('Ellipsis')
    not_implemented = concat.level1.typecheck.PrimitiveType('NotImplemented')
    tuple = concat.level1.typecheck.PrimitiveType(
        'tuple', (
            concat.level1.typecheck.PrimitiveInterfaces.iterable,
        ), {
            '__getitem__': concat.level1.typecheck.PrimitiveTypes.py_function
        }
    )
    base_exception = concat.level1.typecheck.PrimitiveType('BaseException')
    no_return = _NoReturnType()


def infer(
    env: concat.level1.typecheck.Environment,
    program: concat.astutils.WordsOrStatements,
    is_top_level=False,
    extensions=(),
    previous: Tuple[concat.level1.typecheck.Substitutions, concat.level1.typecheck.StackEffect] = (concat.level1.typecheck.Substitutions(), concat.level1.typecheck.StackEffect([], []))
) -> Tuple[concat.level1.typecheck.Substitutions, concat.level1.typecheck.StackEffect]:
    subs, (input, output) = previous
    if isinstance(program[-1], concat.level2.parse.CastWordNode):
        new_type, _ = ast_to_type(program[-1].type, subs, env)
        rest, subs_2 = concat.level1.typecheck.drop_last_from_type_seq(
            list(output))
        effect = subs_2(
            subs(concat.level1.typecheck.StackEffect(input, [*rest, new_type])))
        return subs_2(subs), effect
    elif isinstance(program[-1], concat.level0.parse.ImportStatementNode):
        # TODO: Support all types of import correctly.
        seq_var = concat.level1.typecheck.SequenceVariable()
        # FIXME: We should resolve imports as if we are the source file.
        module = importlib.import_module(program[-1].value)
        module_type: concat.level1.typecheck.Type = concat.level1.typecheck.PrimitiveTypes.module
        for name in dir(module):
            module_type = module_type & concat.level1.typecheck.TypeWithAttribute(
                name, concat.level1.typecheck.PrimitiveTypes.object)
        # mutate type environment
        env[program[-1].value] = concat.level1.typecheck.ForAll([seq_var], concat.level1.typecheck.StackEffect([seq_var],
                                                                                                               [seq_var, module_type]))
        return previous
    elif isinstance(program[-1], concat.level1.parse.FuncdefStatementNode):
        S = subs
        f = concat.level1.typecheck.StackEffect(input, output)
        name = program[-1].name
        declared_type: Optional[concat.level1.typecheck.StackEffect]
        if program[-1].stack_effect:
            declared_type, env_with_types = ast_to_type(
                program[-1].stack_effect, S, S(env))
        else:
            declared_type = None
            env_with_types = env.copy()
        phi1, inferred_type = concat.level1.typecheck.infer(
            S(env_with_types), program[-1].body, is_top_level=False, extensions=extensions)
        if declared_type is not None:
            declared_type = S(declared_type)
            declared_type_inst = concat.level1.typecheck.inst(declared_type)
            inferred_type_inst = concat.level1.typecheck.inst(S(inferred_type))
            # We want to check that the inferred inputs are supertypes of the
            # declared inputs, and that the inferred outputs are subtypes of
            # the declared outputs. Thus, inferred_type should be a subtype
            # declared_type.
            phi2 = concat.level1.typecheck.unify_ind(
                inferred_type_inst, declared_type_inst)
            if not phi2(inferred_type_inst).is_subtype_of(phi2(declared_type_inst)):
                message = ('declared function type {} is not compatible with '
                           'inferred type {}')
                raise TypeError(message.format(
                    phi2(declared_type), phi2(inferred_type)))
            effect = phi2(declared_type)
        else:
            effect = S(inferred_type)
        # we *mutate* the type environment
        env[name] = effect.generalized_wrt(S(env))
        return S, f
    elif isinstance(program[-1], concat.level0.parse.PushWordNode):
        child = program[-1].children[0]
        rest = concat.level1.typecheck.SequenceVariable()
        # special case for subscription words
        if isinstance(child, concat.level1.parse.SubscriptionWordNode):
            S2, (i2, o2) = concat.level1.typecheck.infer(
                subs(env), child.children)
            phi1 = concat.level1.typecheck.unify(S2(output), subs(i2))
            phi2 = concat.level1.typecheck.unify(
                phi1(subs(o2)), [rest, PrimitiveInterfaces.subscriptable, concat.level1.typecheck.PrimitiveTypes.int])
            return phi2(phi1(S2(subs))), phi2(phi1(S2(subs((concat.level1.typecheck.StackEffect(input, [rest, concat.level1.typecheck.PrimitiveTypes.str]))))))
        else:
            raise NotImplementedError(child)
    else:
        raise NotImplementedError


# TODO: Make this a type node method?
@overload
def ast_to_type(ast: AttributeTypeNode, subs: concat.level1.typecheck.Substitutions, env: concat.level1.typecheck.Environment) -> Tuple[concat.level1.typecheck.TypeWithAttribute, concat.level1.typecheck.Environment]:
    ...


@overload
def ast_to_type(ast: StackEffectTypeNode, subs: concat.level1.typecheck.Substitutions, env: concat.level1.typecheck.Environment) -> Tuple[concat.level1.typecheck.StackEffect, concat.level1.typecheck.Environment]:
    ...


@overload
def ast_to_type(ast: IndividualTypeNode, subs: concat.level1.typecheck.Substitutions, env: concat.level1.typecheck.Environment) -> Tuple[concat.level1.typecheck.IndividualType, concat.level1.typecheck.Environment]:
    ...


def ast_to_type(ast: TypeNode, subs: concat.level1.typecheck.Substitutions, env: concat.level1.typecheck.Environment) -> Tuple[concat.level1.typecheck.IndividualType, concat.level1.typecheck.Environment]:
    if isinstance(ast, AttributeTypeNode):
        attr_type, new_env = ast_to_type(ast.type, subs, env)
        return concat.level1.typecheck.TypeWithAttribute(ast.name, attr_type), new_env
    elif isinstance(ast, NamedTypeNode):
        # FIXME: We should look in the environment.
        return getattr(concat.level1.typecheck.PrimitiveTypes, ast.name), env
    elif isinstance(ast, StackEffectTypeNode):
        a_bar = concat.level1.typecheck.SequenceVariable()
        b_bar = a_bar
        new_env = env.copy()
        if ast.input_sequence_variable is not None:
            if ast.input_sequence_variable in env:
                a_bar = cast(concat.level1.typecheck.SequenceVariable,
                             env[ast.input_sequence_variable])
            new_env[ast.input_sequence_variable] = a_bar
        if ast.output_sequence_variable is not None:
            if ast.output_sequence_variable in env:
                b_bar = cast(concat.level1.typecheck.SequenceVariable,
                             env[ast.output_sequence_variable])
            else:
                b_bar = concat.level1.typecheck.SequenceVariable()
                new_env[ast.output_sequence_variable] = b_bar

        in_types = [_ensure_type(item[1], env, item[0]) for item in ast.input]
        out_types = [_ensure_type(item[1], env, item[0]) for item in ast.output]
        return concat.level1.typecheck.StackEffect([a_bar, *in_types], [b_bar, *out_types]), new_env
    elif isinstance(ast, IntersectionTypeNode):
        type_1, new_env = ast_to_type(ast.type_1, subs, env)
        type_2, newer_env = ast_to_type(ast.type_2, subs, new_env)
        return type_1 & type_2, newer_env
    else:
        raise NotImplementedError(ast)


def _ensure_type(
    typename: Union[Optional[NamedTypeNode], StackEffectTypeNode],
    env: concat.level1.typecheck.Environment,
    obj_name: str
) -> concat.level1.typecheck.StackItemType:
    type: concat.level1.typecheck.StackItemType
    if obj_name in env:
        type = cast(concat.level1.typecheck.StackItemType, env[obj_name])
    elif typename is None:
        # REVIEW: If this is the output side of the stack effect, we should
        # default to object. Otherwise, we can end up with sn unbound type
        # variable which will be bound to the first type it's used as. That
        # could lead to some suprising behavior. (???)
        type = concat.level1.typecheck.IndividualVariable()
    elif isinstance(typename, StackEffectTypeNode):
        # FIXME: Don't discard new env
        type, _ = ast_to_type(
            typename, concat.level1.typecheck.Substitutions(), env)
    else:
        try:
            type = getattr(
                concat.level1.typecheck.PrimitiveTypes, typename.name)
        except AttributeError:
            type = getattr(PrimitiveTypes, typename.name)
    env[obj_name] = type
    return type


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

    @parsy.generate
    def stack_effect_type_parser() -> Generator:
        print('parsing stack effect')
        name = parsers.token('NAME')
        individual_type_variable = parsers.token('BACKTICK') >> name >> parsy.success(
            None)
        lpar = parsers.token('LPAR')
        rpar = parsers.token('RPAR')
        nested_stack_effect = lpar >> parsers['stack-effect-type'] << rpar
        type = parsers['type'] | individual_type_variable | nested_stack_effect
        seq_var = parsers.token('STAR') >> name

        separator = parsers.token('MINUS').times(2)

        item = parsy.seq(name, (parsers.token('COLON')
                                >> type).optional()).map(tuple)
        items = item.many()

        stack_effect = parsy.seq(  # type: ignore
            seq_var.optional(), items << separator, seq_var.optional(), items)

        a_bar_parsed, i, b_bar_parsed, o = yield stack_effect

        # FIXME: Get the location
        return StackEffectTypeNode((0, 0), a_bar_parsed, i, b_bar_parsed, o)
    @parsy.generate
    def intersection_type_parser() -> Generator:
        # print('parsing intersection type')
        yield parsers.token('AMPER')
        type_1 = yield parsers['type']
        type_2 = yield parsers['type']
        return IntersectionTypeNode(type_1.location, type_1, type_2)

    parsers['stack-effect-type'] = concat.parser_combinators.desc_cumulatively(
        stack_effect_type_parser, 'stack effect type'
    )

    parsers['type'] = parsy.alt(
        concat.parser_combinators.desc_cumulatively(
            intersection_type_parser, 'intersection type'),
        concat.parser_combinators.desc_cumulatively(
            attribute_type_parser, 'attribute type'),
        concat.parser_combinators.desc_cumulatively(
            named_type_parser, 'named type'),
        parsers.ref_parser('stack-effect-type'),
    )
