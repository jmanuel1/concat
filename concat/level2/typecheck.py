import concat.astutils
import concat.level0.lex
import concat.level0.parse
import concat.level1.typecheck
from concat.level1.typecheck import Environment, TypeError
import concat.level1.parse
import concat.level1.operators
import concat.level2.parse
from concat.level1.typecheck.types import (
    ForAll,
    IndividualType,
    IndividualVariable,
    ObjectType,
    SequenceVariable,
    StackEffect,
    StackItemType,
    Type,
    TypeWithAttribute,
    base_exception_type,
    bool_type,
    context_manager_type,
    dict_type,
    ellipsis_type,
    file_type,
    float_type,
    int_type,
    list_type,
    module_type,
    no_return_type,
    none_type,
    not_implemented_type,
    object_type,
    optional_type,
    py_function_type,
    str_type,
    subtractable_type,
    tuple_type,
)
from typing import Tuple, Generator, Sequence, Optional, Union, cast
import abc
import importlib
import sys
import parsy


class TypeNode(concat.level0.parse.Node, abc.ABC):
    def __init__(self, location: concat.astutils.Location) -> None:
        self.location = location

    @abc.abstractmethod
    def to_type(self, env: Environment) -> Tuple[Type, Environment]:
        pass


class IndividualTypeNode(TypeNode, abc.ABC):
    @abc.abstractmethod
    def __init__(self, location: concat.astutils.Location) -> None:
        super().__init__(location)

    @abc.abstractmethod
    def to_type(self, env: Environment) -> Tuple[IndividualType, Environment]:
        pass


# A dataclass is not used here because making this a subclass of an abstract
# class does not work without overriding __init__ even when it's a dataclass.
class AttributeTypeNode(IndividualTypeNode):
    def __init__(
        self,
        location: concat.astutils.Location,
        name: str,
        type: IndividualTypeNode,
    ) -> None:
        super().__init__(location)
        self.name = name
        self.type = type

    def to_type(
        self, env: Environment
    ) -> Tuple[TypeWithAttribute, Environment]:
        attr_type, new_env = self.type.to_type(env)
        return TypeWithAttribute(self.name, attr_type), new_env


class NamedTypeNode(TypeNode):
    def __init__(self, location: concat.astutils.Location, name: str) -> None:
        super().__init__(location)
        self.name = name

    def __repr__(self) -> str:
        return '{}({!r}, {!r})'.format(
            type(self).__qualname__, self.location, self.name
        )

    def to_type(self, env: Environment) -> Tuple[Type, Environment]:
        type = env.get(self.name, None)
        if type is None:
            raise concat.level1.typecheck.NameError(self.name, self.location)
        return type, env


class StackEffectTypeNode(IndividualTypeNode):
    def __init__(
        self,
        location: concat.astutils.Location,
        in_seq_var: Optional[concat.level0.lex.Token],
        input: Sequence[Tuple[concat.level0.lex.Token, IndividualTypeNode]],
        out_seq_var: Optional[concat.level0.lex.Token],
        output: Sequence[Tuple[concat.level0.lex.Token, IndividualTypeNode]],
    ) -> None:
        super().__init__(location)
        self.input_sequence_variable = in_seq_var.value if in_seq_var else None

        def extract_value(i):
            return (i[0].value, i[1])

        self.input = [extract_value(i) for i in input]
        self.output_sequence_variable = (
            out_seq_var.value if out_seq_var else None
        )
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

    def to_type(self, env: Environment) -> Tuple[StackEffect, Environment]:
        a_bar = concat.level1.typecheck.SequenceVariable()
        b_bar = a_bar
        new_env = env.copy()
        if self.input_sequence_variable is not None:
            if self.input_sequence_variable in env:
                a_bar = cast(
                    concat.level1.typecheck.SequenceVariable,
                    env[self.input_sequence_variable],
                )
            new_env[self.input_sequence_variable] = a_bar
        if self.output_sequence_variable is not None:
            if self.output_sequence_variable in env:
                b_bar = cast(
                    concat.level1.typecheck.SequenceVariable,
                    env[self.output_sequence_variable],
                )
            else:
                b_bar = concat.level1.typecheck.SequenceVariable()
                new_env[self.output_sequence_variable] = b_bar

        in_types = []
        for item in self.input:
            type, new_env = _ensure_type(item[1], new_env, item[0])
            in_types.append(type)
        out_types = []
        for item in self.output:
            type, new_env = _ensure_type(item[1], new_env, item[0])
            out_types.append(type)

        return StackEffect([a_bar, *in_types], [b_bar, *out_types]), new_env


class IntersectionTypeNode(IndividualTypeNode):
    def __init__(
        self,
        location: concat.astutils.Location,
        type_1: IndividualTypeNode,
        type_2: IndividualTypeNode,
    ):
        super().__init__(location)
        self.type_1 = type_1
        self.type_2 = type_2

    def to_type(self, env: Environment) -> Tuple[IndividualType, Environment]:
        type_1, new_env = self.type_1.to_type(env)
        type_2, newer_env = self.type_2.to_type(new_env)
        return type_1 & type_2, newer_env


class _GenericTypeNode(IndividualTypeNode):
    def __init__(
        self,
        location: concat.astutils.Location,
        generic_type: IndividualTypeNode,
        type_arguments: Sequence[IndividualTypeNode],
    ) -> None:
        super().__init__(location)
        self._generic_type = generic_type
        self._type_arguments = type_arguments

    def to_type(self, env: Environment) -> Tuple[IndividualType, Environment]:
        args = []
        for arg in self._type_arguments:
            arg_as_type, env = arg.to_type(env)
            args.append(arg_as_type)
        generic_type, env = self._generic_type.to_type(env)
        if isinstance(generic_type, ObjectType):
            return generic_type[args], env
        raise TypeError('{} is not a generic type'.format(generic_type))


_index_type_var = concat.level1.typecheck.IndividualVariable()
_result_type_var = concat.level1.typecheck.IndividualVariable()
subscriptable_type = ForAll(
    [_index_type_var, _result_type_var],
    TypeWithAttribute(
        '__getitem__',
        py_function_type[(_index_type_var, ), _result_type_var],
    ),
)

# TODO: Separate type-check-time environment from runtime environment.
builtin_environment = Environment(
    {
        'Ellipsis': ellipsis_type,
        'NotImplemented': not_implemented_type,
        'tuple': tuple_type,
        'BaseException': base_exception_type,
        'NoReturn': no_return_type,
        'subscriptable': subscriptable_type,
        'subtractable': subtractable_type,
        'bool': bool_type,
        'object': object_type,
        'context_manager': context_manager_type,
        'dict': dict_type,
        'module': module_type,
        'list': list_type,
        'str': str_type,
        'py_function': py_function_type,
        'None': none_type,
        'Optional': optional_type,
        'int': int_type,
        'float': float_type,
        'file': file_type,
    }
)

_seq_var = concat.level1.typecheck.SequenceVariable()


def _generate_type_of_innermost_module(
    qualified_name: str, source_dir
) -> StackEffect:
    # We resolve imports as if we are the source file.
    sys.path, old_path = [source_dir, *sys.path], sys.path
    module = importlib.import_module(qualified_name)
    sys.path = old_path
    module_t: concat.level1.typecheck.IndividualType = module_type
    for name in dir(module):
        attribute_type = object_type
        if isinstance(getattr(module, name), int):
            attribute_type = int_type
        elif callable(getattr(module, name)):
            attribute_type = py_function_type
        module_t = module_t & TypeWithAttribute(name, attribute_type)
    return StackEffect([_seq_var], [_seq_var, module_type])


def _generate_module_type(
    components: Sequence[str], _full_name: Optional[str] = None, source_dir='.'
) -> ForAll:
    module_t: IndividualType = module_type
    if _full_name is None:
        _full_name = '.'.join(components)
    if len(components) > 1:
        module_t = module_t & TypeWithAttribute(
            components[1],
            _generate_module_type(components[1:], _full_name, source_dir).type,
        )
        effect = StackEffect([_seq_var], [_seq_var, module_type])
        return ForAll([_seq_var], effect)
    else:
        innermost_type = _generate_type_of_innermost_module(
            _full_name, source_dir
        )
        return ForAll([_seq_var], innermost_type)


def infer(
    env: concat.level1.typecheck.Environment,
    program: concat.astutils.WordsOrStatements,
    is_top_level=False,
    extensions=(),
    previous: Tuple[concat.level1.typecheck.Substitutions, StackEffect] = (
        concat.level1.typecheck.Substitutions(),
        StackEffect([], []),
    ),
    source_dir='.',
) -> Tuple[concat.level1.typecheck.Substitutions, StackEffect]:
    subs, (input, output) = previous
    if isinstance(program[-1], concat.level2.parse.CastWordNode):
        new_type, _ = program[-1].type.to_type(env)
        rest, subs_2 = concat.level1.typecheck.drop_last_from_type_seq(
            list(output)
        )
        effect = subs_2(subs(StackEffect(input, [*rest, new_type])))
        return subs_2(subs), effect
    elif isinstance(program[-1], concat.level1.parse.FromImportStatementNode):
        imported_name = program[-1].asname or program[-1].imported_name
        # mutate type environment
        env[imported_name] = object_type
        # We will try to find a more specific type.
        sys.path, old_path = [source_dir, *sys.path], sys.path
        module = importlib.import_module(program[-1].value)
        sys.path = old_path
        # For now, assume the module's written in Python.
        try:
            env[imported_name] = subs(
                getattr(module, '@@types')[program[-1].imported_name]
            )
        except (KeyError, AttributeError):
            # attempt instrospection to get a more specific type
            if callable(getattr(module, program[-1].imported_name)):
                env[imported_name] = py_function_type
        return subs, StackEffect(input, output)
    elif isinstance(program[-1], concat.level1.parse.ImportStatementNode):
        # TODO: Support all types of import correctly.
        seq_var = concat.level1.typecheck.SequenceVariable()
        if program[-1].asname is not None:
            env[program[-1].asname] = subs(
                _generate_type_of_innermost_module(
                    program[-1].value, source_dir
                ).generalized_wrt(subs(env))
            )
        else:
            imported_name = program[-1].value
            # mutate type environment
            components = program[-1].value.split('.')
            # FIXME: This replaces whatever was previously imported. I really
            # should implement namespaces properly.
            env[components[0]] = subs(
                _generate_module_type(components, source_dir=source_dir)
            )
        return subs, StackEffect(input, output)
    elif isinstance(program[-1], concat.level1.parse.SubscriptionWordNode):
        # TODO: This should be a call.
        # FIXME: The object being indexed is not popped before computing the
        # index.
        seq_var = SequenceVariable()
        index_type_var = IndividualVariable()
        result_type_var = IndividualVariable()
        subscriptable_interface = subscriptable_type[
            index_type_var, result_type_var
        ]
        subs_2 = concat.level1.typecheck.unify(
            list(output), [seq_var, subscriptable_interface]
        )
        (
            index_subs,
            (index_input, index_output),
        ) = concat.level1.typecheck.infer(
            subs_2(subs(env)), program[-1].children
        )
        subs_3 = concat.level1.typecheck.unify(
            subs_2(subs([seq_var])), subs_2(subs(index_input))
        )
        seq_var_2 = concat.level1.typecheck.SequenceVariable()

        index_types = [seq_var_2, index_type_var]
        result_types = [seq_var_2, result_type_var]

        final_subs = concat.level1.typecheck.unify(
            subs_3(subs_2(subs(index_output))),
            subs_3(subs_2(subs([*index_types]))),
        )
        final_subs = final_subs(subs_3(subs_2(subs)))
        return final_subs, final_subs(StackEffect(input, result_types))
    elif isinstance(program[-1], concat.level1.parse.FuncdefStatementNode):
        S = subs
        f = StackEffect(input, output)
        name = program[-1].name
        declared_type: Optional[StackEffect]
        if program[-1].stack_effect:
            declared_type, env_with_types = program[-1].stack_effect.to_type(
                S(env)
            )
        else:
            declared_type = None
            env_with_types = env.copy()
        phi1, inferred_type = concat.level1.typecheck.infer(
            S(env_with_types),
            program[-1].body,
            is_top_level=False,
            extensions=extensions,
        )
        if declared_type is not None:
            declared_type = S(declared_type)
            declared_type_inst = concat.level1.typecheck.inst(declared_type)
            inferred_type_inst = concat.level1.typecheck.inst(S(inferred_type))
            # We want to check that the inferred inputs are supertypes of the
            # declared inputs, and that the inferred outputs are subtypes of
            # the declared outputs. Thus, inferred_type should be a subtype
            # declared_type.
            phi2 = concat.level1.typecheck.unify_ind(
                inferred_type_inst, declared_type_inst
            )
            if not phi2(inferred_type_inst).is_subtype_of(
                phi2(declared_type_inst)
            ):
                message = (
                    'declared function type {} is not compatible with '
                    'inferred type {}'
                )
                raise TypeError(
                    message.format(phi2(declared_type), phi2(inferred_type))
                )
            effect = phi2(declared_type)
        else:
            effect = S(inferred_type)
        # we *mutate* the type environment
        env[name] = effect.generalized_wrt(S(env))
        return S, f
    elif isinstance(program[-1], concat.level0.parse.PushWordNode):
        child = program[-1].children[0]
        rest_var = concat.level1.typecheck.SequenceVariable()
        # special case for subscription words
        if isinstance(child, concat.level1.parse.SubscriptionWordNode):
            S2, (i2, o2) = concat.level1.typecheck.infer(
                subs(env), child.children, extensions=extensions
            )
            phi1 = concat.level1.typecheck.unify(S2(output), subs(i2))
            # FIXME: Should be generic
            subscriptable_interface = subscriptable_type[
                int_type, str_type,
            ]
            expected_o2 = [
                rest_var,
                subscriptable_interface,
                int_type,
            ]
            phi2 = concat.level1.typecheck.unify(phi1(subs(o2)), expected_o2)
            effect = phi2(
                phi1(S2(subs((StackEffect(input, [rest_var, str_type],)))))
            )
            return phi2(phi1(S2(subs))), effect
        else:
            raise NotImplementedError(child)
    else:
        raise NotImplementedError


def _ensure_type(
    typename: Union[Optional[NamedTypeNode], StackEffectTypeNode],
    env: concat.level1.typecheck.Environment,
    obj_name: str,
) -> Tuple[Type, concat.level1.typecheck.Environment]:
    type: Type
    if obj_name in env:
        type = cast(StackItemType, env[obj_name])
    elif typename is None:
        # NOTE: This could lead type varibles in the output of a function that
        # are unconstrained. In other words, it would basically become an Any
        # type.
        type = IndividualVariable()
    elif isinstance(typename, (NamedTypeNode, StackEffectTypeNode)):
        type, env = typename.to_type(env)
    else:
        raise NotImplementedError(
            'Cannot turn {!r} into a type'.format(typename)
        )
    env[obj_name] = type
    return type, env


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
        individual_type_variable = (
            parsers.token('BACKTICK') >> name >> parsy.success(None)
        )
        lpar = parsers.token('LPAR')
        rpar = parsers.token('RPAR')
        nested_stack_effect = lpar >> parsers['stack-effect-type'] << rpar
        type = parsers['type'] | individual_type_variable | nested_stack_effect
        seq_var = parsers.token('STAR') >> name

        separator = parsers.token('MINUS').times(2)

        item = parsy.seq(
            name, (parsers.token('COLON') >> type).optional()
        ).map(tuple)
        items = item.many()

        stack_effect = parsy.seq(  # type: ignore
            seq_var.optional(), items << separator, seq_var.optional(), items
        )

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

    @parsy.generate
    def generic_type_parser() -> Generator:
        type = yield parsers['nonparameterized-type']
        yield parsers.token('LSQB')
        type_arguments = yield parsers['type'].sep_by(
            parsers.token('COMMA'), 1
        )
        yield parsers.token('RSQB')
        return _GenericTypeNode(type.location, type, type_arguments)

    parsers['nonparameterized-type'] = parsy.alt(
        concat.parser_combinators.desc_cumulatively(
            intersection_type_parser, 'intersection type'
        ),
        concat.parser_combinators.desc_cumulatively(
            attribute_type_parser, 'attribute type'
        ),
        concat.parser_combinators.desc_cumulatively(
            named_type_parser, 'named type'
        ),
        parsers.ref_parser('stack-effect-type'),
    )

    parsers['type'] = parsy.alt(
        concat.parser_combinators.desc_cumulatively(
            generic_type_parser, 'generic type'
        ),
        parsers.ref_parser('nonparameterized-type'),
    )
