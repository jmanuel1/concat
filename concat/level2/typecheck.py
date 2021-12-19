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
    PythonFunctionType,
    SequenceVariable,
    StackEffect,
    StackItemType,
    StackMismatchError,
    Type,
    TypeSequence,
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
from typing import (
    Iterable,
    List,
    Tuple,
    Generator,
    Sequence,
    Optional,
    Union,
    cast,
)
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
        self,
        args: Sequence[Union[concat.level0.lex.Token, IndividualTypeNode]],
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
        seq_var: Optional[str],
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
        elif self._sequence_variable not in env:
            env = env.copy()
            env[self._sequence_variable] = SequenceVariable()
            sequence.append(env[self._sequence_variable])
        for type_node in self._individual_type_items:
            type, env = type_node.to_type(env)
            sequence.append(type)
        return TypeSequence(sequence), env

    @property
    def sequence_variable(self) -> Optional[str]:
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


_index_type_var = concat.level1.typecheck.IndividualVariable()
_result_type_var = concat.level1.typecheck.IndividualVariable()
subscriptable_type = ObjectType(
    IndividualVariable(),
    {
        '__getitem__': py_function_type[
            TypeSequence([_index_type_var]), _result_type_var
        ],
    },
    [_index_type_var, _result_type_var],
)

# TODO: Separate type-check-time environment from runtime environment.
_stack_type_var = SequenceVariable()
builtin_environment = Environment(
    {
        # XXX: generalize to_int over the stack
        'to_int': StackEffect(
            TypeSequence(
                [_stack_type_var, optional_type[int_type,], object_type]
            ),
            TypeSequence([_stack_type_var, int_type]),
        ),
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
        rest = output[:-1]
        effect = subs(StackEffect(input, [*rest, new_type]))
        return subs, effect
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
            # attempt introspection to get a more specific type
            if callable(getattr(module, program[-1].imported_name)):
                args_var = SequenceVariable()
                env[imported_name] = ObjectType(
                    IndividualVariable(),
                    {
                        '__call__': py_function_type[
                            TypeSequence([args_var]), object_type
                        ],
                    },
                    type_parameters=[args_var],
                    nominal=True,
                )
        return subs, StackEffect(input, output)
    elif isinstance(program[-1], concat.level1.parse.ImportStatementNode):
        # TODO: Support all types of import correctly.
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
        seq = output[:-1]
        index_type_var = IndividualVariable()
        result_type_var = IndividualVariable()
        subscriptable_interface = subscriptable_type[
            index_type_var, result_type_var
        ]
        (
            index_subs,
            (index_input, index_output),
        ) = concat.level1.typecheck.infer(
            subs(env), program[-1].children, initial_stack=output
        )
        index_output_typeseq = index_output
        subs = index_output_typeseq[-2].constrain_and_bind_supertype_variables(
            subscriptable_interface, set(),
        )(index_subs(subs))
        subs(index_output_typeseq[-1]).constrain(subs(index_type_var))

        result_type = subs(result_type_var).get_type_of_attribute('__call__')
        if not isinstance(result_type, StackEffect):
            raise TypeError(
                'result of subscription is not callable as a Concat function (has type {})'.format(
                    result_type
                )
            )
        subs = index_output_typeseq[
            :-2
        ].constrain_and_bind_supertype_variables(result_type.input, set())(
            subs
        )

        return subs, subs(StackEffect(input, result_type.output))
    elif isinstance(program[-1], concat.level1.operators.SubtractWordNode):
        # FIXME: We should check if the other operand supports __rsub__ if the
        # first operand doesn't support __sub__.
        other_operand_type_var = concat.level1.typecheck.IndividualVariable()
        result_type_var = concat.level1.typecheck.IndividualVariable()
        subtractable_interface = subtractable_type[
            other_operand_type_var, result_type_var
        ]
        seq_var = concat.level1.typecheck.SequenceVariable()
        final_subs = output.constrain_and_bind_supertype_variables(
            TypeSequence(
                [seq_var, subtractable_interface, other_operand_type_var]
            ),
            set(),
        )
        assert seq_var in final_subs
        return (
            final_subs(subs),
            final_subs(StackEffect(input, [seq_var, result_type_var])),
        )
    elif isinstance(program[-1], concat.level1.parse.FuncdefStatementNode):
        S = subs
        f = StackEffect(input, output)
        name = program[-1].name
        declared_type: Optional[StackEffect]
        if program[-1].stack_effect:
            declared_type, _ = program[-1].stack_effect.to_type(S(env))
            declared_type = S(declared_type)
        else:
            # NOTE: To continue the "bidirectional" bent, we will require a
            # type annotation.
            # TODO: Make the return types optional?
            # FIXME: Should be a parse error.
            raise TypeError('must have type annotation on function definition')
        recursion_env = env.copy()
        recursion_env[name] = declared_type.generalized_wrt(S(env))
        phi1, inferred_type = concat.level1.typecheck.infer(
            S(recursion_env),
            program[-1].body,
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
            # print(phi1)
            raise TypeError(message.format(declared_type, inferred_type))
        effect = declared_type
        # we *mutate* the type environment
        env[name] = effect.generalized_wrt(S(env))
        return S, f
    elif isinstance(program[-1], concat.level0.parse.PushWordNode):
        child = program[-1].children[0]
        # special case for subscription words
        if isinstance(child, concat.level1.parse.SubscriptionWordNode):
            S2, (i2, o2) = concat.level1.typecheck.infer(
                subs(env),
                child.children,
                extensions=extensions,
                is_top_level=False,
                source_dir=source_dir,
                initial_stack=TypeSequence(output),
            )
            # FIXME: Should be generic
            subscriptable_interface = subscriptable_type[
                int_type, IndividualVariable(),
            ]

            rest_var = concat.level1.typecheck.SequenceVariable()
            expected_o2 = TypeSequence(
                [rest_var, subscriptable_interface, int_type,]
            )
            o2[-1].constrain(int_type)
            getitem_type = (
                o2[-2]
                .get_type_of_attribute('__getitem__')
                .instantiate()
                .get_type_of_attribute('__call__')
                .instantiate()
            )
            if not isinstance(getitem_type, PythonFunctionType):
                raise TypeError(
                    '__getitem__ of type {} is not a Python function (has type {})'.format(
                        o2[-2], getitem_type
                    )
                )
            getitem_type, overload_subs = getitem_type.select_overload(
                [int_type]
            )
            subs = overload_subs(S2(subs))
            effect = subs(StackEffect(input, [*o2[:-2], getitem_type.output]))
            return subs, effect
        else:
            raise NotImplementedError(child)
    elif isinstance(
        program[-1], concat.level1.operators.GreaterThanOrEqualToWordNode
    ):
        a_type, b_type = output[-2:]
        try:
            ge_type = a_type.get_type_of_attribute('__ge__')
            if not isinstance(ge_type, PythonFunctionType):
                raise TypeError(
                    'method __ge__ of type {} should be a Python function'.format(
                        ge_type
                    )
                )
            _, subs = ge_type.select_overload([b_type])
        except TypeError:
            le_type = b_type.get_type_of_attribute('__le__')
            if not isinstance(le_type, PythonFunctionType):
                raise TypeError(
                    'method __le__ of type {} should be a Python function'.format(
                        le_type
                    )
                )
            _, subs = le_type.select_overload([a_type])
        return (
            subs,
            StackEffect(input, TypeSequence([*output[:-2], bool_type])),
        )
    elif isinstance(
        program[-1],
        (
            concat.level1.operators.IsWordNode,
            concat.level1.operators.AndWordNode,
            concat.level1.operators.OrWordNode,
            concat.level1.operators.EqualToWordNode,
        ),
    ):
        # TODO: I should be more careful here, since at least __eq__ can be
        # deleted, if I remember correctly.
        if not isinstance(output[-1], IndividualType) or not isinstance(
            output[-2], IndividualType
        ):
            raise StackMismatchError(
                TypeSequence(output), TypeSequence([object_type, object_type])
            )
        return (
            subs,
            StackEffect(input, TypeSequence([*output[:-2], bool_type])),
        )
    else:
        raise NotImplementedError(program[-1])


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
        type = concat.level1.typecheck.IndividualVariable()
    elif isinstance(
        typename, (_GenericTypeNode, NamedTypeNode, StackEffectTypeNode)
    ):
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
        raise NotImplementedError('better think about the syntax of this')

    @parsy.generate
    def named_type_parser() -> Generator:
        name_token = yield parsers.token('NAME')
        return NamedTypeNode(name_token.start, name_token.value)

    @parsy.generate
    def type_sequence_parser() -> Generator:
        name = parsers.token('NAME')
        individual_type_variable = (
            # FIXME: Keep track of individual type variables
            parsers.token('BACKTICK')
            >> name
            >> parsy.success(None)
        )
        lpar = parsers.token('LPAR')
        rpar = parsers.token('RPAR')
        nested_stack_effect = lpar >> parsers['stack-effect-type'] << rpar
        type = parsers['type'] | individual_type_variable | nested_stack_effect

        # TODO: Allow type-only items
        item = parsy.seq(
            name, (parsers.token('COLON') >> type).optional()
        ).map(_TypeSequenceIndividualTypeNode)
        items = item.many()

        seq_var = parsers.token('STAR') >> name
        seq_var_parsed, i = yield parsy.seq(seq_var.optional(), items)
        seq_var_value = None

        if seq_var_parsed is None and i:
            location = i[0].location
        elif seq_var_parsed is not None:
            location = seq_var_parsed.start
            seq_var_value = seq_var_parsed.value
        else:
            location = None

        return TypeSequenceNode(location, seq_var_value, i)

    @parsy.generate
    def stack_effect_type_parser() -> Generator:
        separator = parsers.token('MINUS').times(2)

        stack_effect = parsy.seq(  # type: ignore
            parsers['type-sequence'] << separator, parsers['type-sequence']
        )

        i, o = yield stack_effect

        # FIXME: Get the location
        return StackEffectTypeNode((0, 0), i, o)

    @parsy.generate
    def intersection_type_parser() -> Generator:
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
            parsers.token('COMMA'), min=1
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

    parsers['type-sequence'] = concat.parser_combinators.desc_cumulatively(
        type_sequence_parser, 'type sequence'
    )
