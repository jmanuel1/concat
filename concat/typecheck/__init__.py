"""The Concat type checker.

The type inference algorithm was originally based on the one described in
"Robert Kleffner: A Foundation for Typed Concatenative Languages, April 2017."
"""

import abc
import builtins
import collections.abc
from concat.lex import Token
import importlib
import sys
from typing import (
    Generator,
    Iterable,
    List,
    Set,
    Tuple,
    Dict,
    Union,
    Optional,
    Callable,
    Sequence,
    TypeVar,
    TYPE_CHECKING,
    overload,
    cast,
)
from typing_extensions import Protocol
import parsy
import concat.parse


if TYPE_CHECKING:
    import concat.astutils
    from concat.typecheck.types import _Variable


class StaticAnalysisError(Exception):
    def __init__(self, message: str) -> None:
        self._message = message
        self.location: Optional['concat.astutils.Location'] = None

    def set_location_if_missing(
        self, location: 'concat.astutils.Location'
    ) -> None:
        if not self.location:
            self.location = location

    def __str__(self) -> str:
        return '{} at {}'.format(self._message, self.location)


class TypeError(StaticAnalysisError, builtins.TypeError):
    pass


class NameError(StaticAnalysisError, builtins.NameError):
    def __init__(
        self,
        name: Union[concat.parse.NameWordNode, str],
        location: Optional[concat.astutils.Location] = None,
    ) -> None:
        if isinstance(name, concat.parse.NameWordNode):
            location = name.location
            name = name.value
        super().__init__(name)
        self._name = name
        self.location = location or self.location

    def __str__(self) -> str:
        location_info = ''
        if self.location:
            location_info = ' (error at {}:{})'.format(*self.location)
        return (
            'name "{}" not previously defined'.format(self._name)
            + location_info
        )


class AttributeError(TypeError, builtins.AttributeError):
    def __init__(self, type: 'Type', attribute: str) -> None:
        super().__init__(
            'object of type {} does not have attribute {}'.format(
                type, attribute
            )
        )
        self._type = type
        self._attribute = attribute


class StackMismatchError(TypeError):
    def __init__(
        self, actual: 'TypeSequence', expected: 'TypeSequence'
    ) -> None:
        super().__init__(
            'The stack here is {}, but sequence type {} was expected'.format(
                actual, expected
            )
        )


class UnhandledNodeTypeError(builtins.NotImplementedError):
    pass


_Result = TypeVar('_Result', covariant=True)


class _Substitutable(Protocol[_Result]):
    def apply_substitution(self, sub: 'Substitutions') -> _Result:
        pass


class Substitutions(Dict['_Variable', 'Type']):
    def __call__(self, arg: _Substitutable[_Result]) -> _Result:
        return arg.apply_substitution(self)

    def _dom(self) -> Set['_Variable']:
        return {*self}

    def __str__(self) -> str:
        return (
            '{'
            + ',\n'.join(
                map(lambda i: '{}: {}'.format(i[0], i[1]), self.items())
            )
            + '}'
        )

    def apply_substitution(self, sub: 'Substitutions') -> 'Substitutions':
        return Substitutions(
            {
                **sub,
                **{a: sub(i) for a, i in self.items() if a not in sub._dom()},
            }
        )


from concat.typecheck.types import (
    Type,
    IndividualVariable,
    StackEffect,
    ForAll,
    IndividualType,
    ObjectType,
    PythonFunctionType,
    SequenceVariable,
    TypeSequence,
    StackItemType,
    QuotationType,
    bool_type,
    context_manager_type,
    ellipsis_type,
    int_type,
    init_primitives,
    invertible_type,
    iterable_type,
    list_type,
    module_type,
    none_type,
    not_implemented_type,
    object_type,
    py_function_type,
    slice_type,
    str_type,
    subscriptable_type,
    subtractable_type,
    tuple_type,
)


class Environment(Dict[str, Type]):
    def copy(self) -> 'Environment':
        return Environment(super().copy())

    def apply_substitution(self, sub: 'Substitutions') -> 'Environment':
        return Environment({name: sub(t) for name, t in self.items()})


def check(
    environment: Environment,
    program: concat.astutils.WordsOrStatements,
    source_dir: str = '.',
) -> None:
    import concat.typecheck.preamble_types

    environment = Environment(
        {**concat.typecheck.preamble_types.types, **environment}
    )
    infer(environment, program, None, True, source_dir)


# FIXME: I'm really passing around a bunch of state here. I could create an
# object to store it, or turn this algorithm into an object.
def infer(
    gamma: Environment,
    e: 'concat.astutils.WordsOrStatements',
    extensions: Optional[Tuple[Callable]] = None,
    is_top_level=False,
    source_dir='.',
    initial_stack: Optional[TypeSequence] = None,
) -> Tuple[Substitutions, StackEffect]:
    """The infer function described by Kleffner."""
    e = list(e)
    current_subs = Substitutions()
    if initial_stack is None:
        initial_stack = TypeSequence(
            [] if is_top_level else [SequenceVariable()]
        )
    current_effect = StackEffect(initial_stack, initial_stack)

    for node in e:
        try:
            S, (i, o) = current_subs, current_effect

            if isinstance(node, concat.parse.PushWordNode):
                S1, (i1, o1) = S, (i, o)
                child = node.children[0]
                if isinstance(child, concat.parse.FreezeWordNode):
                    should_instantiate = False
                    child = child.word
                else:
                    should_instantiate = True
                # special case for pushing an attribute accessor
                if isinstance(child, concat.parse.AttributeWordNode):
                    top = o1[-1]
                    attr_type = top.get_type_of_attribute(child.value)
                    if should_instantiate:
                        attr_type = attr_type.instantiate()
                    rest_types = o1[:-1]
                    current_subs, current_effect = (
                        S1,
                        StackEffect(i1, [*rest_types, attr_type]),
                    )
                # special case for name words
                elif isinstance(child, concat.parse.NameWordNode):
                    if child.value not in gamma:
                        raise NameError(child)
                    name_type = gamma[child.value]
                    if should_instantiate:
                        name_type = name_type.instantiate()
                    current_effect = StackEffect(
                        current_effect.input,
                        [*current_effect.output, current_subs(name_type)],
                    )
                elif isinstance(child, concat.parse.QuoteWordNode):
                    if child.input_stack_type is not None:
                        input_stack, _ = child.input_stack_type.to_type(gamma)
                    else:
                        # The majority of quotations I've written don't comsume
                        # anything on the stack, so make that the default.
                        input_stack = TypeSequence([SequenceVariable()])
                    S2, fun_type = infer(
                        S1(gamma),
                        child.children,
                        extensions=extensions,
                        source_dir=source_dir,
                        initial_stack=input_stack,
                    )
                    current_subs, current_effect = (
                        S2(S1),
                        StackEffect(
                            S2(TypeSequence(i1)),
                            [*S2(TypeSequence(o1)), QuotationType(fun_type)],
                        ),
                    )
                else:
                    raise UnhandledNodeTypeError(
                        'quoted word {} (repr {!r})'.format(child, child)
                    )
            elif isinstance(node, concat.parse.ListWordNode):
                phi = S
                collected_type = TypeSequence(o)
                element_type: IndividualType = object_type
                for item in node.list_children:
                    phi1, fun_type = infer(
                        phi(gamma),
                        item,
                        extensions=extensions,
                        source_dir=source_dir,
                        initial_stack=collected_type,
                    )
                    collected_type = fun_type.output
                    # FIXME: Infer the type of elements in the list based on
                    # ALL the elements.
                    if element_type == object_type:
                        assert isinstance(collected_type[-1], IndividualType)
                        element_type = collected_type[-1]
                    # drop the top of the stack to use as the item
                    collected_type = collected_type[:-1]
                    phi = phi1(phi)
                current_subs, current_effect = (
                    phi,
                    phi(
                        StackEffect(
                            i, [*collected_type, list_type[element_type,]]
                        )
                    ),
                )
            elif isinstance(node, concat.parse.TupleWordNode):
                phi = S
                collected_type = current_effect.output
                element_types: List[IndividualType] = []
                for item in node.tuple_children:
                    phi1, fun_type = infer(
                        phi(gamma),
                        item,
                        extensions=extensions,
                        source_dir=source_dir,
                        initial_stack=collected_type,
                    )
                    collected_type = fun_type.output
                    assert isinstance(collected_type[-1], IndividualType)
                    element_types.append(collected_type[-1])
                    # drop the top of the stack to use as the item
                    collected_type = collected_type[:-1]
                    phi = phi1(phi)
                current_subs, current_effect = (
                    phi,
                    phi(
                        StackEffect(
                            i,
                            [
                                *collected_type,
                                tuple_type[TypeSequence(element_types),],
                            ],
                        )
                    ),
                )
            elif isinstance(node, concat.parse.FromImportStatementNode):
                imported_name = node.asname or node.imported_name
                # mutate type environment
                gamma[imported_name] = object_type
                # We will try to find a more specific type.
                sys.path, old_path = [source_dir, *sys.path], sys.path
                module = importlib.import_module(node.value)
                sys.path = old_path
                # For now, assume the module's written in Python.
                try:
                    # TODO: Support star imports
                    gamma[imported_name] = current_subs(
                        getattr(module, '@@types')[node.imported_name]
                    )
                except (KeyError, builtins.AttributeError):
                    # attempt introspection to get a more specific type
                    if callable(getattr(module, node.imported_name)):
                        args_var = SequenceVariable()
                        gamma[imported_name] = ObjectType(
                            IndividualVariable(),
                            {
                                '__call__': py_function_type[
                                    TypeSequence([args_var]), object_type
                                ],
                            },
                            type_parameters=[args_var],
                            nominal=True,
                        )
            elif isinstance(node, concat.parse.ImportStatementNode):
                # TODO: Support all types of import correctly.
                if node.asname is not None:
                    gamma[node.asname] = current_subs(
                        _generate_type_of_innermost_module(
                            node.value, source_dir
                        ).generalized_wrt(current_subs(gamma))
                    )
                else:
                    imported_name = node.value
                    # mutate type environment
                    components = node.value.split('.')
                    # FIXME: This replaces whatever was previously imported. I really
                    # should implement namespaces properly.
                    gamma[components[0]] = current_subs(
                        _generate_module_type(
                            components, source_dir=source_dir
                        )
                    )
            elif isinstance(node, concat.parse.FuncdefStatementNode):
                S = current_subs
                f = current_effect
                name = node.name
                # NOTE: To continue the "bidirectional" bent, we will require a
                # type annotation.
                # TODO: Make the return types optional?
                declared_type, _ = node.stack_effect.to_type(S(gamma))
                declared_type = S(declared_type)
                recursion_env = gamma.copy()
                recursion_env[name] = declared_type.generalized_wrt(S(gamma))
                phi1, inferred_type = infer(
                    S(recursion_env),
                    node.body,
                    is_top_level=False,
                    extensions=extensions,
                    initial_stack=declared_type.input,
                )
                # We want to check that the inferred outputs are subtypes of
                # the declared outputs. Thus, inferred_type.output should be a subtype
                # declared_type.output.
                try:
                    inferred_type.output.constrain(declared_type.output)
                except TypeError:
                    message = (
                        'declared function type {} is not compatible with '
                        'inferred type {}'
                    )
                    raise TypeError(
                        message.format(declared_type, inferred_type)
                    )
                effect = declared_type
                # we *mutate* the type environment
                gamma[name] = effect.generalized_wrt(S(gamma))
            elif isinstance(node, concat.parse.NumberWordNode):
                if isinstance(node.value, int):
                    current_effect = StackEffect(i, [*o, int_type])
                else:
                    raise UnhandledNodeTypeError
            elif isinstance(node, concat.parse.NameWordNode):
                (i1, o1) = current_effect
                if node.value not in current_subs(gamma):
                    raise NameError(node)
                type_of_name = current_subs(gamma)[node.value].instantiate()
                type_of_name = type_of_name.get_type_of_attribute(
                    '__call__'
                ).instantiate()
                if not isinstance(type_of_name, StackEffect):
                    raise UnhandledNodeTypeError(
                        'name {} of type {} (repr {!r})'.format(
                            node.value, type_of_name, type_of_name
                        )
                    )
                constraint_subs = o1.constrain_and_bind_supertype_variables(
                    type_of_name.input, set(), []
                )
                current_subs = constraint_subs(current_subs)
                current_effect = current_subs(
                    StackEffect(i1, type_of_name.output)
                )
            elif isinstance(node, concat.parse.QuoteWordNode):
                quotation = cast(concat.parse.QuoteWordNode, node)
                # make sure any annotation matches the current stack
                if quotation.input_stack_type is not None:
                    input_stack, _ = quotation.input_stack_type.to_type(gamma)
                    S = TypeSequence(o).constrain_and_bind_supertype_variables(
                        input_stack, set(), []
                    )(S)
                else:
                    input_stack = TypeSequence(o)
                S1, (i1, o1) = infer(
                    gamma,
                    [*quotation.children],
                    extensions=extensions,
                    source_dir=source_dir,
                    initial_stack=input_stack,
                )
                current_subs, current_effect = (
                    S1(S),
                    S1(StackEffect(i, o1)),
                )
            elif isinstance(node, concat.parse.StringWordNode):
                current_subs, current_effect = (
                    S,
                    StackEffect(
                        current_effect.input,
                        [*current_effect.output, str_type],
                    ),
                )
            elif isinstance(node, concat.parse.AttributeWordNode):
                stack_top_type = o[-1]
                out_types = o[:-1]
                attr_function_type = stack_top_type.get_type_of_attribute(
                    node.value
                ).instantiate()
                if not isinstance(attr_function_type, StackEffect):
                    raise UnhandledNodeTypeError(
                        'attribute {} of type {} (repr {!r})'.format(
                            node.value, attr_function_type, attr_function_type
                        )
                    )
                R = TypeSequence(
                    out_types
                ).constrain_and_bind_supertype_variables(
                    attr_function_type.input, set(), []
                )
                current_subs, current_effect = (
                    R(S),
                    R(StackEffect(i, attr_function_type.output)),
                )
            elif isinstance(node, concat.parse.CastWordNode):
                new_type, _ = node.type.to_type(gamma)
                rest = current_effect.output[:-1]
                current_effect = current_subs(
                    StackEffect(current_effect.input, [*rest, new_type])
                )
            else:
                raise UnhandledNodeTypeError(
                    "don't know how to handle '{}'".format(node)
                )
        except TypeError as e:
            e.set_location_if_missing(node.location)
            raise
    return current_subs, current_effect


# Parsing type annotations


class TypeNode(concat.parse.Node, abc.ABC):
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
            raise NameError(self.name, self.location)
        return type, env


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
        raise NotImplementedError('intersection types should longer exist')


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


class _TypeSequenceIndividualTypeNode(IndividualTypeNode):
    def __init__(
        self, args: Sequence[Union[concat.lex.Token, IndividualTypeNode]],
    ) -> None:
        if args[0] is None:
            location = args[1].location
        else:
            location = args[0].start
        super().__init__(location)
        self._name = None if args[0] is None else args[0].value
        self._type = args[1]

    # QUESTION: Should I have a separate space for the temporary associated names?
    def to_type(self, env: Environment) -> Tuple[IndividualType, Environment]:
        if self._name is None:
            return self._type.to_type(env)
        elif self._type is None:
            return env[self._name].to_type(env)
        elif self._name in env:
            raise TypeError(
                '{} is associated with a type more than once in this sequence of types'.format(
                    self._name
                )
            )
        else:
            type, env = self._type.to_type(env)
            env = env.copy()
            env[self._name] = type
            return type, env

    @property
    def name(self) -> Optional[str]:
        return self._name

    @property
    def type(self) -> Optional[IndividualTypeNode]:
        return self._type


class TypeSequenceNode(TypeNode):
    def __init__(
        self,
        location: Optional[concat.astutils.Location],
        seq_var: Optional['_SequenceVariableNode'],
        individual_type_items: Iterable[_TypeSequenceIndividualTypeNode],
    ) -> None:
        super().__init__(location or (-1, -1))
        self._sequence_variable = seq_var
        self._individual_type_items = tuple(individual_type_items)

    def to_type(self, env: Environment) -> Tuple[TypeSequence, Environment]:
        sequence: List[StackItemType] = []
        if self._sequence_variable is None:
            # implicit stack polymorphism
            sequence.append(SequenceVariable())
        elif self._sequence_variable.name not in env:
            env = env.copy()
            var = SequenceVariable()
            env[self._sequence_variable.name] = var
            sequence.append(var)
        for type_node in self._individual_type_items:
            type, env = type_node.to_type(env)
            sequence.append(type)
        return TypeSequence(sequence), env

    @property
    def sequence_variable(self) -> Optional['_SequenceVariableNode']:
        return self._sequence_variable

    @property
    def individual_type_items(
        self,
    ) -> Sequence[_TypeSequenceIndividualTypeNode]:
        return self._individual_type_items


class StackEffectTypeNode(IndividualTypeNode):
    def __init__(
        self,
        location: concat.astutils.Location,
        input: TypeSequenceNode,
        output: TypeSequenceNode,
    ) -> None:
        super().__init__(location)
        self.input_sequence_variable = input.sequence_variable
        self.input = [(i.name, i.type) for i in input.individual_type_items]
        self.output_sequence_variable = output.sequence_variable
        self.output = [(o.name, o.type) for o in output.individual_type_items]

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
        a_bar = SequenceVariable()
        b_bar = a_bar
        new_env = env.copy()
        if self.input_sequence_variable is not None:
            if self.input_sequence_variable.name in new_env:
                a_bar = cast(
                    SequenceVariable,
                    new_env[self.input_sequence_variable.name],
                )
            new_env[self.input_sequence_variable.name] = a_bar
        if self.output_sequence_variable is not None:
            if self.output_sequence_variable.name in new_env:
                b_bar = cast(
                    SequenceVariable,
                    new_env[self.output_sequence_variable.name],
                )
            else:
                b_bar = SequenceVariable()
                new_env[self.output_sequence_variable.name] = b_bar

        in_types = []
        for item in self.input:
            type, new_env = _ensure_type(item[1], new_env, item[0])
            in_types.append(type)
        out_types = []
        for item in self.output:
            type, new_env = _ensure_type(item[1], new_env, item[0])
            out_types.append(type)

        return StackEffect([a_bar, *in_types], [b_bar, *out_types]), new_env


class _IndividualVariableNode(IndividualTypeNode):
    def __init__(self, name: Token) -> None:
        super().__init__(name.start)
        self._name = name.value

    def to_type(
        self, env: Environment
    ) -> Tuple[IndividualVariable, Environment]:
        # QUESTION: Should callers be expected to have already introduced the
        # name into the context?
        if self._name in env:
            type = env[self._name]
            if not isinstance(type, IndividualVariable):
                error = TypeError(
                    '{} is not an individual type variable'.format(self._name)
                )
                error.location = self.location
                raise error
            return type, env

        env = env.copy()
        var = IndividualVariable()
        env[self._name] = var
        return var, env

    @property
    def name(self) -> str:
        return self._name


class _SequenceVariableNode(TypeNode):
    def __init__(self, name: Token) -> None:
        super().__init__(name.start)
        self._name = name.value

    def to_type(
        self, env: Environment
    ) -> Tuple[SequenceVariable, Environment]:
        # QUESTION: Should callers be expected to have already introduced the
        # name into the context?
        if self._name in env:
            type = env[self._name]
            if not isinstance(type, SequenceVariable):
                error = TypeError(
                    '{} is not an sequence type variable'.format(self._name)
                )
                error.location = self.location
                raise error
            return type, env

        env = env.copy()
        var = SequenceVariable()
        env[self._name] = var
        return var, env

    @property
    def name(self) -> str:
        return self._name


class _ForallTypeNode(TypeNode):
    def __init__(
        self,
        location: 'concat.astutils.Location',
        type_variables: Sequence[
            Union[_IndividualVariableNode, _SequenceVariableNode]
        ],
        type: TypeNode,
    ) -> None:
        super().__init__(location)
        self._type_variables = type_variables
        self._type = type

    def to_type(self, env: Environment) -> Tuple[Type, Environment]:
        temp_env = env.copy()
        vars = []
        for var in self._type_variables:
            parameter, temp_env = var.to_type(temp_env)
            vars.append(parameter)
        type, _ = self._type.to_type(temp_env)
        forall_type = ForAll(vars, type)
        return forall_type, env


def typecheck_extension(parsers: concat.parse.ParserDict) -> None:
    @parsy.generate
    def non_star_name_parser() -> Generator:
        name = yield parsers.token('NAME')
        if name.value == '*':
            yield parsy.fail('name that is not star (*)')
        return name

    @parsy.generate
    def named_type_parser() -> Generator:
        name_token = yield parsers.token('NAME')
        return NamedTypeNode(name_token.start, name_token.value)

    @parsy.generate
    def individual_type_variable_parser() -> Generator:
        yield parsers.token('BACKTICK')
        name = yield non_star_name_parser

        return _IndividualVariableNode(name)

    @parsy.generate
    def sequence_type_variable_parser() -> Generator:
        star = yield parsers.token('NAME')
        if star.value != '*':
            yield parsy.fail('star (*)')
        name = yield non_star_name_parser

        return _SequenceVariableNode(name)

    @parsy.generate
    def type_sequence_parser() -> Generator:
        type = parsers['type'] | individual_type_variable_parser

        # TODO: Allow type-only items
        item = parsy.seq(
            non_star_name_parser, (parsers.token('COLON') >> type).optional()
        ).map(_TypeSequenceIndividualTypeNode)
        items = item.many()

        seq_var = sequence_type_variable_parser
        seq_var_parsed: Optional[_SequenceVariableNode]
        seq_var_parsed = yield seq_var.optional()
        i = yield items
        seq_var_value = None

        if seq_var_parsed is None and i:
            location = i[0].location
        elif seq_var_parsed is not None:
            location = seq_var_parsed.location
        else:
            location = None

        return TypeSequenceNode(location, seq_var_parsed, i)

    @parsy.generate
    def stack_effect_type_parser() -> Generator:
        separator = parsers.token('MINUSMINUS')

        location = (yield parsers.token('LPAR')).start

        i = yield parsers['type-sequence'] << separator
        o = yield parsers['type-sequence']

        yield parsers.token('RPAR')

        return StackEffectTypeNode(location, i, o)

    parsers['stack-effect-type'] = concat.parser_combinators.desc_cumulatively(
        stack_effect_type_parser, 'stack effect type'
    )

    @parsy.generate
    def generic_type_parser() -> Generator:
        type = yield parsers['nonparameterized-type']
        yield parsers.token('LSQB')
        type_arguments = yield parsers['type'].sep_by(
            parsers.token('COMMA'), min=1
        )
        yield parsers.token('RSQB')
        return _GenericTypeNode(type.location, type, type_arguments)

    @parsy.generate
    def forall_type_parser() -> Generator:
        forall = yield parsers.token('NAME')
        if forall.value != 'forall':
            yield parsy.fail('the word "forall"')

        type_variables = yield (
            individual_type_variable_parser | sequence_type_variable_parser
        ).at_least(1)

        yield parsers.token('DOT')

        type = yield parsers['type']

        return _ForallTypeNode(forall.start, type_variables, type)

    # TODO: Parse type variables
    parsers['nonparameterized-type'] = parsy.alt(
        concat.parser_combinators.desc_cumulatively(
            named_type_parser, 'named type'
        ),
        parsers.ref_parser('stack-effect-type'),
    )

    parsers['type'] = parsy.alt(
        # NOTE: There's a parsing ambiguity that might come back to bite me...
        concat.parser_combinators.desc_cumulatively(
            forall_type_parser, 'forall type'
        ),
        concat.parser_combinators.desc_cumulatively(
            generic_type_parser, 'generic type'
        ),
        parsers.ref_parser('nonparameterized-type'),
    )

    parsers['type-sequence'] = concat.parser_combinators.desc_cumulatively(
        type_sequence_parser, 'type sequence'
    )


_seq_var = SequenceVariable()


def _generate_type_of_innermost_module(
    qualified_name: str, source_dir
) -> StackEffect:
    # We resolve imports as if we are the source file.
    sys.path, old_path = [source_dir, *sys.path], sys.path
    try:
        module = importlib.import_module(qualified_name)
    except ModuleNotFoundError:
        raise TypeError(
            'module {} not found during type checking'.format(qualified_name)
        )
    finally:
        sys.path = old_path
    module_attributes = {}
    for name in dir(module):
        attribute_type = object_type
        if isinstance(getattr(module, name), int):
            attribute_type = int_type
        elif callable(getattr(module, name)):
            attribute_type = py_function_type
        module_attributes[name] = attribute_type
    module_t = ObjectType(
        IndividualVariable(),
        module_attributes,
        nominal_supertypes=[module_type],
    )
    return StackEffect([_seq_var], [_seq_var, module_type])


def _generate_module_type(
    components: Sequence[str], _full_name: Optional[str] = None, source_dir='.'
) -> ObjectType:
    if _full_name is None:
        _full_name = '.'.join(components)
    if len(components) > 1:
        module_t = ObjectType(
            IndividualVariable(),
            {
                components[1]: _generate_module_type(
                    components[1:], _full_name, source_dir
                )[_seq_var,],
            },
            nominal_supertypes=[module_type],
        )
        effect = StackEffect([_seq_var], [_seq_var, module_type])
        return ObjectType(
            IndividualVariable(), {'__call__': effect,}, [_seq_var]
        )
    else:
        innermost_type = _generate_type_of_innermost_module(
            _full_name, source_dir
        )
        return ObjectType(
            IndividualVariable(), {'__call__': innermost_type,}, [_seq_var]
        )


def _ensure_type(
    typename: Optional[TypeNode], env: Environment, obj_name: Optional[str],
) -> Tuple[StackItemType, Environment]:
    type: StackItemType
    if obj_name and obj_name in env:
        type = cast(StackItemType, env[obj_name])
    elif typename is None:
        # NOTE: This could lead type varibles in the output of a function that
        # are unconstrained. In other words, it would basically become an Any
        # type.
        type = IndividualVariable()
    elif isinstance(typename, TypeNode):
        type, env = cast(
            Tuple[StackItemType, Environment], typename.to_type(env)
        )
    else:
        raise NotImplementedError(
            'Cannot turn {!r} into a type'.format(typename)
        )
    if obj_name:
        env[obj_name] = type
    return type, env


init_primitives()
