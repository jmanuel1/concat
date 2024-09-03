import abc
from concat.orderedset import InsertionOrderedSet
import concat.typecheck
from concat.typecheck.errors import (
    AttributeError as ConcatAttributeError,
    StackMismatchError,
    StaticAnalysisError,
    TypeError as ConcatTypeError,
)
import functools
from typing import (
    AbstractSet,
    Any,
    Dict,
    Iterable,
    Iterator,
    List,
    Mapping,
    NoReturn,
    Optional,
    Sequence,
    TYPE_CHECKING,
    Tuple,
    TypeVar,
    Union,
    cast,
    overload,
)


if TYPE_CHECKING:
    from concat.typecheck import Environment, Substitutions


class SubtypeExplanation:
    def __init__(self, data: Any) -> None:
        self._data = data

    def __bool__(self) -> bool:
        if isinstance(self._data, concat.typecheck.Substitutions):
            return not self._data
        return not isinstance(self._data, StaticAnalysisError)

    def __str__(self) -> str:
        if isinstance(self._data, StaticAnalysisError):
            e: Optional[BaseException] = self._data
            string = ''
            while e is not None:
                string += '\n' + str(e)
                e = e.__cause__ or e.__context__
            return string
        if isinstance(self._data, concat.typecheck.Substitutions):
            string = str(self._data)
            string += '\n' + '\n'.join(
                (map(str, self._data.subtyping_provenance))
            )
            return string
        return str(self._data)


class Type(abc.ABC):
    _next_type_id = 0

    def __init__(self) -> None:
        self._free_type_variables_cached: Optional[
            InsertionOrderedSet[Variable]
        ] = None
        self._internal_name: Optional[str] = None
        self._type_id = Type._next_type_id
        Type._next_type_id += 1

    # QUESTION: Do I need this?
    def is_subtype_of(self, supertype: 'Type') -> SubtypeExplanation:
        from concat.typecheck import Substitutions

        try:
            sub = self.constrain_and_bind_variables(supertype, set(), [])
        except ConcatTypeError as e:
            return SubtypeExplanation(e)
        ftv = self.free_type_variables() | supertype.free_type_variables()
        sub1 = Substitutions({v: t for v, t in sub.items() if v in ftv})
        sub1.subtyping_provenance = sub.subtyping_provenance
        return SubtypeExplanation(sub1)

    # No <= implementation using subtyping, because variables overload that for
    # sort by identity.

    def __eq__(self, other: object) -> bool:
        if self is other:
            return True
        if not isinstance(other, Type):
            return NotImplemented
        # QUESTION: Define == separately from is_subtype_of?
        return self.is_subtype_of(other) and other.is_subtype_of(self)  # type: ignore

    # NOTE: Avoid hashing types. I might I'm having correctness issues related
    # to hashing that I'd rather avoid entirely. Maybe one day I'll introduce
    # hash consing, but that would only reflect syntactic eequality, and I've
    # been using hashing for type equality.

    def get_type_of_attribute(self, name: str) -> 'Type':
        attributes = self.attributes
        if name not in attributes:
            raise ConcatAttributeError(self, name)
        return attributes[name]

    def has_attribute(self, name: str) -> bool:
        try:
            self.get_type_of_attribute(name)
            return True
        except ConcatAttributeError:
            return False

    @abc.abstractproperty
    def attributes(self) -> Mapping[str, 'Type']:
        return {}

    @abc.abstractmethod
    def _free_type_variables(self) -> InsertionOrderedSet['Variable']:
        pass

    def free_type_variables(self) -> InsertionOrderedSet['Variable']:
        if self._free_type_variables_cached is None:
            # Break circular references. Recusring into the same type won't add
            # new FTVs, so we can pretend there are none we finish finding the
            # others.
            self._free_type_variables_cached = InsertionOrderedSet([])
            self._free_type_variables_cached = self._free_type_variables()
        return self._free_type_variables_cached

    @abc.abstractmethod
    def apply_substitution(
        self, _: 'concat.typecheck.Substitutions'
    ) -> 'Type':
        pass

    @abc.abstractmethod
    def constrain_and_bind_variables(
        self,
        supertype: 'Type',
        rigid_variables: AbstractSet['Variable'],
        subtyping_assumptions: List[Tuple['Type', 'Type']],
    ) -> 'Substitutions':
        raise NotImplementedError

    # QUESTION: Should I remove this? Should I not distinguish between subtype
    # and supertype variables in the other two constraint methods? I should
    # look bidirectional typing with polymorphism/generics. Maybe 'Complete and
    # Easy'?
    def constrain(self, supertype: 'Type') -> None:
        if not self.is_subtype_of(supertype):
            raise ConcatTypeError(
                '{} is not a subtype of {}'.format(self, supertype)
            )

    def instantiate(self) -> 'Type':
        return self

    @abc.abstractproperty
    def kind(self) -> 'Kind':
        pass

    def set_internal_name(self, name: str) -> None:
        self._internal_name = name

    def __str__(self) -> str:
        if self._internal_name is not None:
            return self._internal_name
        return super().__str__()

    def __getitem__(self, _: Any) -> Any:
        raise ConcatTypeError(
            f'{self} is neither a generic type nor a sequence type'
        )


class IndividualType(Type):
    def instantiate(self) -> 'IndividualType':
        return cast(IndividualType, super().instantiate())

    @property
    def kind(self) -> 'Kind':
        return IndividualKind

    @property
    def attributes(self) -> Mapping[str, Type]:
        return {}


class StuckTypeApplication(IndividualType):
    def __init__(self, head: Type, args: 'TypeArguments') -> None:
        super().__init__()
        self._head = head
        self._args = args

    def apply_substitution(self, sub: 'Substitutions') -> Type:
        return sub(self._head)[[sub(t) for t in self._args]]

    def constrain_and_bind_variables(
        self, supertype, rigid_variables, subtyping_assumptions
    ) -> 'Substitutions':
        from concat.typecheck import Substitutions

        if self is supertype or supertype is get_object_type():
            return Substitutions()
        if isinstance(supertype, StuckTypeApplication):
            # TODO: Variance
            return self._head.constrain_and_bind_variables(
                supertype._head, rigid_variables, subtyping_assumptions
            )
        raise ConcatTypeError(
            f'Cannot deduce that {self} is a subtype of {supertype} here'
        )

    def __str__(self) -> str:
        if self._internal_name is not None:
            return self._internal_name
        return f'{self._head}{_iterable_to_str(self._args)}'

    def __repr__(self) -> str:
        return f'StuckTypeApplication({self._head!r}, {self._args!r})'

    def _free_type_variables(self) -> InsertionOrderedSet['Variable']:
        ftv = self._head.free_type_variables()
        for arg in self._args:
            ftv |= arg.free_type_variables()
        return ftv


class Variable(Type, abc.ABC):
    """Objects that represent type variables.

    Every type variable object is assumed to be unique. Thus, fresh type
    variables can be made simply by creating new objects. They can also be
    compared by identity."""

    def apply_substitution(
        self, sub: 'concat.typecheck.Substitutions'
    ) -> Type:
        if self in sub:
            result = sub[self]
            return result  # type: ignore
        return self

    def _free_type_variables(self) -> InsertionOrderedSet['Variable']:
        return InsertionOrderedSet([self])

    def __lt__(self, other) -> bool:
        """Comparator for storing variables in OrderedSets."""
        return id(self) < id(other)

    def __gt__(self, other) -> bool:
        """Comparator for storing variables in OrderedSets."""
        return id(self) > id(other)

    def __eq__(self, other) -> bool:
        return self is other

    # NOTE: This hash impl is kept because sets of variables are fine and
    # variables are simple.
    def __hash__(self) -> int:
        """Hash a variable by its identity.

        __hash__ by object identity is used since that's the only way for two
        type variables to be ==."""

        return hash(id(self))

    @abc.abstractmethod
    def freshen(self) -> 'Variable':
        pass


class BoundVariable(Variable):
    def __init__(self, kind: 'Kind') -> None:
        super().__init__()
        self._kind = kind

    @property
    def kind(self) -> 'Kind':
        return self._kind

    def constrain_and_bind_variables(
        self, supertype, rigid_variables, subtyping_assumptions
    ) -> 'Substitutions':
        from concat.typecheck import Substitutions

        if (
            self._type_id == supertype._type_id
            or supertype._type_id == get_object_type()._type_id
            or (self, supertype) in subtyping_assumptions
        ):
            return Substitutions()
        if (
            isinstance(supertype, Variable)
            and self.kind <= supertype.kind
            and supertype not in rigid_variables
        ):
            return Substitutions([(supertype, self)])
        raise ConcatTypeError(
            f'Cannot constrain bound variable {self} to {supertype}'
        )

    def __getitem__(self, args: 'TypeArguments') -> Type:
        if not isinstance(self.kind, GenericTypeKind):
            raise ConcatTypeError(f'{self} is not a generic type')
        if len(self.kind.parameter_kinds) != len(args):
            raise ConcatTypeError(
                f'{self} was given {len(args)} arguments but expected {len(self.kind.parameter_kinds)}'
            )
        for a, p in zip(args, self.kind.parameter_kinds):
            if not (a.kind <= p):
                raise ConcatTypeError(
                    f'{a} has kind {a.kind} but expected kind {p}'
                )
        return StuckTypeApplication(self, args)

    def __repr__(self) -> str:
        return f'<bound variable {id(self)}>'

    def __str__(self) -> str:
        return f't_{id(self)}'

    @property
    def attributes(self) -> Mapping[str, Type]:
        raise TypeError('Cannot get attributes of bound variables')

    def freshen(self) -> 'Variable':
        if self._kind <= ItemKind:
            return ItemVariable(self._kind)
        return SequenceVariable()


class ItemVariable(Variable):
    def __init__(self, kind: 'Kind') -> None:
        super().__init__()
        self._kind = kind

    def constrain_and_bind_variables(
        self,
        supertype: Type,
        rigid_variables: AbstractSet['Variable'],
        subtyping_assumptions: List[Tuple['Type', 'Type']],
    ) -> 'Substitutions':
        from concat.typecheck import Substitutions

        if (
            self is supertype
            # QUESTION: subsumption of polytypes?
            or self.kind is IndividualKind
            and supertype._type_id is get_object_type()._type_id
        ):
            return Substitutions()
        if (
            isinstance(supertype, Variable)
            and self.kind <= supertype.kind
            and supertype not in rigid_variables
        ):
            return Substitutions([(supertype, self)])
        mapping: Mapping[Variable, Type]
        if self.kind is IndividualKind and isinstance(
            supertype, _OptionalType
        ):
            try:
                return self.constrain_and_bind_variables(
                    supertype.type_arguments[0],
                    rigid_variables,
                    subtyping_assumptions,
                )
            except ConcatTypeError:
                return self.constrain_and_bind_variables(
                    get_none_type(), rigid_variables, subtyping_assumptions
                )
        if self in rigid_variables:
            raise ConcatTypeError(
                f'{self} is considered fixed here and cannot become a subtype of {supertype}'
            )
        if self.kind >= supertype.kind:
            mapping = {self: supertype}
            return Substitutions(mapping)
        raise ConcatTypeError(
            f'{self} has kind {self.kind}, but {supertype} has kind {supertype.kind}'
        )

    def __str__(self) -> str:
        return 't_{}'.format(id(self))

    def __repr__(self) -> str:
        return '<item variable {}>'.format(id(self))

    @property
    def attributes(self) -> NoReturn:
        raise ConcatTypeError(
            f'{self} is an item type variable, so its attributes are unknown'
        )

    @property
    def kind(self) -> 'Kind':
        return self._kind

    def freshen(self) -> 'ItemVariable':
        return ItemVariable(self._kind)


class SequenceVariable(Variable):
    def __init__(self) -> None:
        super().__init__()

    def __str__(self) -> str:
        return '*t_{}'.format(id(self))

    def __repr__(self) -> str:
        return f'<sequence variable {id(self)}>'

    def constrain_and_bind_variables(
        self,
        supertype: Type,
        rigid_variables: AbstractSet['Variable'],
        subtyping_assumptions: List[Tuple['Type', 'Type']],
    ) -> 'Substitutions':
        from concat.typecheck import Substitutions

        if not isinstance(supertype, (SequenceVariable, TypeSequence)):
            raise ConcatTypeError(
                '{} must be a sequence type, not {}'.format(self, supertype)
            )
        if (
            isinstance(supertype, SequenceVariable)
            and supertype not in rigid_variables
        ):
            sub = Substitutions([(supertype, self)])
            sub.add_subtyping_provenance((self, supertype))
            return sub
        if self in rigid_variables:
            raise ConcatTypeError(
                '{} is fixed here and cannot become a subtype of another type'.format(
                    self
                )
            )
        # occurs check
        if self is not supertype and self in supertype.free_type_variables():
            raise ConcatTypeError(
                '{} cannot be a subtype of {} because it appears in {}'.format(
                    self, supertype, supertype
                )
            )
        sub = Substitutions([(self, supertype)])
        sub.add_subtyping_provenance((self, supertype))
        return sub

    @property
    def attributes(self) -> NoReturn:
        raise ConcatTypeError(
            'the sequence type {} does not hold attributes'.format(self)
        )

    @property
    def kind(self) -> 'Kind':
        return SequenceKind

    def freshen(self) -> 'SequenceVariable':
        return SequenceVariable()


class GenericType(Type):
    def __init__(
        self,
        type_parameters: Sequence['Variable'],
        body: Type,
        is_variadic: bool = False,
    ) -> None:
        super().__init__()
        assert type_parameters
        self._type_parameters = type_parameters
        self._body = body
        self._instantiations: Dict[Tuple[int, ...], Type] = {}
        self.is_variadic = is_variadic

    def __str__(self) -> str:
        if self._internal_name is not None:
            return self._internal_name
        if self.is_variadic:
            params = str(self._type_parameters[0]) + '...'
        else:
            params = ' '.join(map(str, self._type_parameters))

        return f'forall {params}. {self._body}'

    def __repr__(self) -> str:
        return f'{type(self).__qualname__}({self._type_parameters!r}, {self._body!r}, is_variadic={self.is_variadic!r})'

    def __getitem__(self, type_arguments: 'TypeArguments') -> 'Type':
        from concat.typecheck import Substitutions

        type_argument_ids = tuple(t._type_id for t in type_arguments)
        if type_argument_ids in self._instantiations:
            return self._instantiations[type_argument_ids]
        expected_kinds = [var.kind for var in self._type_parameters]
        if self.is_variadic:
            type_arguments = [TypeSequence(type_arguments)]
        actual_kinds = [ty.kind for ty in type_arguments]
        if len(expected_kinds) != len(actual_kinds) or not (
            expected_kinds >= actual_kinds
        ):
            raise ConcatTypeError(
                f'A type argument to {self} has the wrong kind, type arguments: {type_arguments}, expected kinds: {expected_kinds}'
            )
        sub = Substitutions(zip(self._type_parameters, type_arguments))
        instance = sub(self._body)
        self._instantiations[type_argument_ids] = instance
        if self._internal_name is not None:
            instance_internal_name = self._internal_name
            instance_internal_name += (
                '[' + ', '.join(map(str, type_arguments)) + ']'
            )
            instance.set_internal_name(instance_internal_name)
        return instance

    @property
    def kind(self) -> 'GenericTypeKind':
        kinds = [var.kind for var in self._type_parameters]
        return GenericTypeKind(kinds, self._body.kind)

    def instantiate(self) -> Type:
        fresh_vars: Sequence[Variable] = [
            var.freshen() for var in self._type_parameters
        ]
        return self[fresh_vars]

    def constrain_and_bind_variables(
        self,
        supertype: 'Type',
        rigid_variables: AbstractSet['Variable'],
        subtyping_assumptions: List[Tuple['Type', 'Type']],
    ) -> 'Substitutions':
        from concat.typecheck import Substitutions

        if self is supertype or _contains_assumption(
            subtyping_assumptions, self, supertype
        ):
            return Substitutions()
        # NOTE: Here, we implement subsumption of polytypes, so the kinds don't
        # need to be the same. See concat/poly-subsumption.md for more
        # information.
        if (
            isinstance(supertype, Variable)
            and supertype not in rigid_variables
            and self.kind <= supertype.kind
        ):
            return Substitutions([(supertype, self)])
        if not isinstance(supertype, GenericType):
            supertype_parameter_kinds: Sequence[Kind]
            if isinstance(supertype.kind, GenericTypeKind):
                supertype_parameter_kinds = supertype.kind.parameter_kinds
            elif self.kind.result_kind <= supertype.kind:
                supertype_parameter_kinds = []
            else:
                raise ConcatTypeError(
                    f'{self} has kind {self.kind} but {supertype} has kind {supertype.kind}'
                )
            params_to_inst = len(self.kind.parameter_kinds) - len(
                supertype_parameter_kinds
            )
            param_kinds_left = self.kind.parameter_kinds[
                -len(supertype_parameter_kinds) :
            ]
            if params_to_inst < 0 or not (
                param_kinds_left >= supertype_parameter_kinds
            ):
                raise ConcatTypeError(
                    f'{self} has kind {self.kind} but {supertype} has kind {supertype.kind}'
                )
            sub = Substitutions(
                [
                    (t, t.freshen())
                    for t in self._type_parameters[:params_to_inst]
                ]
            )
            parameters_left = self._type_parameters[params_to_inst:]
            inst: Type
            if parameters_left:
                inst = GenericType(parameters_left, sub(self._body))
            else:
                inst = sub(self._body)
            return inst.constrain_and_bind_variables(
                supertype, rigid_variables, subtyping_assumptions
            )
        # supertype is a GenericType
        # QUESTION: Should I care about is_variadic?
        if any(
            map(
                lambda t: t in self.free_type_variables(),
                supertype._type_parameters,
            )
        ):
            raise ConcatTypeError(
                f'Type parameters {supertype._type_parameters} cannot appear free in {self}'
            )
        return self.instantiate().constrain_and_bind_variables(
            supertype._body,
            rigid_variables | set(supertype._type_parameters),
            subtyping_assumptions,
        )

    def apply_substitution(self, sub: 'Substitutions') -> 'GenericType':
        from concat.typecheck import Substitutions

        sub = Substitutions(
            {
                var: ty
                for var, ty in sub.items()
                if var not in self._type_parameters
            }
        )
        ty = GenericType(
            self._type_parameters,
            sub(self._body),
            is_variadic=self.is_variadic,
        )
        return ty

    @property
    def attributes(self) -> NoReturn:
        raise ConcatTypeError(
            'Generic types do not have attributes; maybe you forgot type arguments?'
        )

    def _free_type_variables(self) -> InsertionOrderedSet['Variable']:
        return self._body.free_type_variables() - set(self._type_parameters)


class TypeSequence(Type, Iterable[Type]):
    def __init__(self, sequence: Sequence[Type]) -> None:
        super().__init__()
        self._rest: Optional[SequenceVariable]
        if sequence and isinstance(sequence[0], SequenceVariable):
            self._rest = sequence[0]
            self._individual_types = sequence[1:]
        else:
            self._rest = None
            self._individual_types = sequence
        for ty in self._individual_types:
            if ty.kind == SequenceKind:
                raise ConcatTypeError(f'{ty} cannot be a sequence type')

    def as_sequence(self) -> Sequence[Type]:
        if self._rest is not None:
            return [self._rest, *self._individual_types]
        return self._individual_types

    def apply_substitution(self, sub) -> 'TypeSequence':
        if all(v not in self.free_type_variables() for v in sub):
            return self

        subbed_types: List[StackItemType] = []
        for type in self:
            subbed_type: Union[StackItemType, TypeSequence] = sub(type)
            if isinstance(subbed_type, TypeSequence):
                subbed_types += [*subbed_type]
            else:
                subbed_types.append(subbed_type)
        return TypeSequence(subbed_types)

    def constrain_and_bind_variables(
        self,
        supertype: Type,
        rigid_variables: AbstractSet['Variable'],
        subtyping_assumptions: List[Tuple['Type', 'Type']],
    ) -> 'Substitutions':
        """Check that self is a subtype of supertype.

        Free type variables that appear in either type sequence are set to be
        equal to their counterparts in the other sequence so that type
        information can be propagated into calls of named functions.
        """
        from concat.typecheck import Substitutions

        if self is supertype or _contains_assumption(
            subtyping_assumptions, self, supertype
        ):
            sub = Substitutions()
            sub.add_subtyping_provenance((self, supertype))
            return sub

        if isinstance(supertype, SequenceVariable):
            supertype = TypeSequence([supertype])

        if isinstance(supertype, TypeSequence):
            if self._is_empty():
                # [] <: []
                if supertype._is_empty():
                    sub = Substitutions()
                    sub.add_subtyping_provenance((self, supertype))
                    return sub
                # [] <: *a, *a is not rigid
                # --> *a = []
                elif (
                    self._is_empty()
                    and supertype._rest
                    and not supertype._individual_types
                    and supertype._rest not in rigid_variables
                ):
                    sub = Substitutions([(supertype._rest, self)])
                    sub.add_subtyping_provenance((self, supertype))
                    return sub
                # [] <: *a? `t0 `t...
                # error
                else:
                    raise StackMismatchError(self, supertype)
            if not self._individual_types:
                # *a <: [], *a is not rigid
                # --> *a = []
                if supertype._is_empty() and self._rest not in rigid_variables:
                    assert self._rest is not None
                    sub = Substitutions([(self._rest, supertype)])
                    sub.add_subtyping_provenance((self, supertype))
                    return sub
                # *a <: *a
                if (
                    self._rest is supertype._rest
                    and not supertype._individual_types
                ):
                    sub = Substitutions()
                    sub.add_subtyping_provenance((self, supertype))
                    return sub
                # *a <: *b? `t..., *a is not rigid, *a is not free in RHS
                # --> *a = RHS
                if (
                    self._rest
                    and self._rest not in rigid_variables
                    and self._rest not in supertype.free_type_variables()
                ):
                    sub = Substitutions([(self._rest, supertype)])
                    sub.add_subtyping_provenance((self, supertype))
                    return sub
            # *a? `t... `t_n <: []
            # error
            if supertype._is_empty():
                raise StackMismatchError(self, supertype)
            # *a? `t... `t_n <: *b, *b is not rigid, *b is not free in LHS
            # --> *b = LHS
            elif (
                not supertype._individual_types
                and supertype._rest
                and supertype._rest not in self.free_type_variables()
                and supertype._rest not in rigid_variables
            ):
                sub = Substitutions([(supertype._rest, self)])
                sub.add_subtyping_provenance((self, supertype))
                return sub
            # `t_n <: `s_m  *a? `t... <: *b? `s...
            #   ---
            # *a? `t... `t_n <: *b? `s... `s_m
            elif supertype._individual_types:
                sub = self._individual_types[-1].constrain_and_bind_variables(
                    supertype._individual_types[-1],
                    rigid_variables,
                    subtyping_assumptions,
                )
                try:
                    sub = sub(self[:-1]).constrain_and_bind_variables(
                        sub(supertype[:-1]),
                        rigid_variables,
                        subtyping_assumptions,
                    )(sub)
                    return sub
                except StackMismatchError:
                    # TODO: Add info about occurs check and rigid
                    # variables.
                    raise StackMismatchError(self, supertype)
            else:
                raise StackMismatchError(self, supertype)
            raise StackMismatchError(self, supertype)
        else:
            raise ConcatTypeError(
                f'{self} is a sequence type, not {supertype}'
            )

    def _free_type_variables(self) -> InsertionOrderedSet['Variable']:
        ftv: InsertionOrderedSet[Variable] = InsertionOrderedSet([])
        for t in self:
            ftv |= t.free_type_variables()
        return ftv

    @property
    def attributes(self) -> NoReturn:
        raise ConcatTypeError(
            'the sequence type {} does not hold attributes'.format(self)
        )

    def __bool__(self) -> bool:
        return not self._is_empty()

    def _is_empty(self) -> bool:
        return self._rest is None and not self._individual_types

    @overload
    def __getitem__(self, key: int) -> 'StackItemType':
        ...

    @overload
    def __getitem__(self, key: slice) -> 'TypeSequence':
        ...

    def __getitem__(self, key: Union[int, slice]) -> Type:
        if isinstance(key, int):
            return self.as_sequence()[key]
        return TypeSequence(self.as_sequence()[key])

    def __str__(self) -> str:
        return '[' + ', '.join(str(t) for t in self) + ']'

    def __repr__(self) -> str:
        return 'TypeSequence([' + ', '.join(repr(t) for t in self) + '])'

    def __iter__(self) -> Iterator[Type]:
        return iter(self.as_sequence())

    @property
    def kind(self) -> 'Kind':
        return SequenceKind


# TODO: Rename to StackEffect at all use sites.
class _Function(IndividualType):
    def __init__(
        self, input_types: TypeSequence, output_types: TypeSequence,
    ) -> None:
        super().__init__()
        self.input = input_types
        self.output = output_types

    def __iter__(self) -> Iterator['TypeSequence']:
        return iter((self.input, self.output))

    def generalized_wrt(self, gamma: 'Environment') -> Type:
        parameters = list(
            self.free_type_variables() - gamma.free_type_variables()
        )
        return GenericType(parameters, self)

    def constrain_and_bind_variables(
        self,
        supertype: Type,
        rigid_variables: AbstractSet['Variable'],
        subtyping_assumptions: List[Tuple['Type', 'Type']],
    ) -> 'Substitutions':
        from concat.typecheck import Substitutions

        if (
            self is supertype
            or _contains_assumption(subtyping_assumptions, self, supertype)
            or supertype._type_id == get_object_type()._type_id
        ):
            return Substitutions()

        if (
            isinstance(supertype, ItemVariable)
            and supertype.kind <= ItemKind
            and supertype not in rigid_variables
        ):
            return Substitutions([(supertype, self)])
        if isinstance(supertype, _OptionalType):
            return self.constrain_and_bind_variables(
                supertype.type_arguments[0],
                rigid_variables,
                subtyping_assumptions,
            )
        if not isinstance(supertype, StackEffect):
            raise ConcatTypeError(
                '{} is not a subtype of {}'.format(self, supertype)
            )
        # Remember that the input should be contravariant!
        sub = supertype.input.constrain_and_bind_variables(
            self.input, rigid_variables, subtyping_assumptions
        )
        sub = sub(self.output).constrain_and_bind_variables(
            sub(supertype.output), rigid_variables, subtyping_assumptions
        )(sub)
        return sub

    def _free_type_variables(self) -> InsertionOrderedSet['Variable']:
        return (
            self.input.free_type_variables()
            | self.output.free_type_variables()
        )

    @staticmethod
    def _rename_sequence_variable(
        supertype_list: Sequence['StackItemType'],
        subtype_list: Sequence['StackItemType'],
        sub: 'concat.typecheck.Substitutions',
    ) -> bool:
        both_lists_nonempty = supertype_list and subtype_list
        if (
            both_lists_nonempty
            and isinstance(supertype_list[0], SequenceVariable)
            and isinstance(subtype_list[0], SequenceVariable)
        ):
            if supertype_list[0] not in sub:
                # FIXME: Treat sub immutably, or better yet, don't use
                # substitutions here if possible
                sub._sub[supertype_list[0]] = subtype_list[0]
            else:
                if sub(supertype_list[0]) is not subtype_list[0]:
                    return False
        return True

    def __repr__(self) -> str:
        return '{}({!r}, {!r})'.format(
            type(self).__qualname__, self.input, self.output
        )

    def __str__(self) -> str:
        in_types = ' '.join(map(str, self.input))
        out_types = ' '.join(map(str, self.output))
        return '({} -- {})'.format(in_types, out_types)

    @property
    def attributes(self) -> Mapping[str, 'StackEffect']:
        return {'__call__': self}

    def apply_substitution(
        self, sub: 'concat.typecheck.Substitutions'
    ) -> '_Function':
        return _Function(sub(self.input), sub(self.output))

    def bind(self) -> '_Function':
        return _Function(self.input[:-1], self.output)


class QuotationType(_Function):
    def __init__(self, fun_type: _Function) -> None:
        super().__init__(fun_type.input, fun_type.output)

    def constrain_and_bind_variables(
        self,
        supertype: Type,
        rigid_variables: AbstractSet['Variable'],
        subtyping_assumptions: List[Tuple['Type', 'Type']],
    ) -> 'Substitutions':
        if (
            isinstance(supertype, ObjectType)
            and supertype.head == iterable_type
        ):
            # FIXME: Don't present new variables every time.
            # FIXME: Account for the types of the elements of the quotation.
            in_var = ItemVariable(IndividualKind)
            out_var = ItemVariable(IndividualKind)
            quotation_iterable_type = iterable_type[
                StackEffect(TypeSequence([in_var]), TypeSequence([out_var])),
            ]
            return quotation_iterable_type.constrain_and_bind_variables(
                supertype, rigid_variables, subtyping_assumptions
            )
        return super().constrain_and_bind_variables(
            supertype, rigid_variables, subtyping_assumptions
        )

    def apply_substitution(
        self, sub: 'concat.typecheck.Substitutions'
    ) -> 'QuotationType':
        return QuotationType(super().apply_substitution(sub))


StackItemType = Union[SequenceVariable, IndividualType]


def free_type_variables_of_mapping(
    attributes: Mapping[str, Type]
) -> InsertionOrderedSet[Variable]:
    ftv: InsertionOrderedSet[Variable] = InsertionOrderedSet([])
    for sigma in attributes.values():
        ftv |= sigma.free_type_variables()
    return ftv


TypeArguments = Sequence[Type]
_T = TypeVar('_T')


def _contains_assumption(
    assumptions: Sequence[Tuple[Type, Type]], subtype: Type, supertype: Type
) -> bool:
    for sub, sup in assumptions:
        if (
            sub._type_id == subtype._type_id
            and sup._type_id == supertype._type_id
        ):
            return True
    return False


# The representation of types of objects.

# Originally, it was based on a gradual typing paper. That paper is "Design and
# Evaluation of Gradual Typing for Python" (Vitousek et al. 2014). But now
# nominal and structural subtyping will be separated internally by using
# brands, like in "Integrating Nominal and Structural Subtyping" (Malayeri &
# Aldrich 2008).

# http://reports-archive.adm.cs.cmu.edu/anon/anon/home/ftp/usr0/ftp/2008/CMU-CS-08-120.pdf

# not using functools.total_ordering because == should be only identity.
class Brand:
    def __init__(
        self, user_name: str, kind: 'Kind', superbrands: Sequence['Brand']
    ) -> None:
        self._user_name = user_name
        self.kind = kind
        # for t in superbrands:
        #     if t.kind != kind:
        #         raise ConcatTypeError(
        #             f'{t} must have kind {kind}, but has kind {t.kind}'
        #         )
        self._superbrands = superbrands

    def __str__(self) -> str:
        return self._user_name

    def __repr__(self) -> str:
        return f'Brand({self._user_name!r}, {self.kind}, {self._superbrands!r})@{id(self)}'

    def __lt__(self, other: 'Brand') -> bool:
        object_brand = get_object_type().unroll().brand  # type: ignore
        return (
            (self is not other and other is object_brand)
            or other in self._superbrands
            or any(brand <= other for brand in self._superbrands)
        )

    def __le__(self, other: 'Brand') -> bool:
        return self is other or self < other


class NominalType(Type):
    def __init__(self, brand: Brand, ty: Type) -> None:
        super().__init__()

        self._brand = brand
        self._ty = ty
        # assert brand.kind == ty.kind

    def _free_type_variables(self) -> InsertionOrderedSet[Variable]:
        return self._ty.free_type_variables()

    def apply_substitution(self, sub: 'Substitutions') -> 'NominalType':
        return NominalType(self._brand, sub(self._ty))

    @property
    def attributes(self) -> Mapping[str, Type]:
        return self._ty.attributes

    def constrain_and_bind_variables(
        self, supertype, rigid_variables, subtyping_assumptions
    ) -> 'Substitutions':
        if isinstance(supertype, NominalType):
            if self._brand <= supertype._brand:
                return concat.typecheck.Substitutions()
            raise ConcatTypeError(f'{self} is not a subtype of {supertype}')
        # TODO: Find a way to force myself to handle these different cases.
        # Visitor pattern? singledispatch?
        if isinstance(supertype, _OptionalType):
            try:
                return self.constrain_and_bind_variables(
                    get_none_type(), rigid_variables, subtyping_assumptions
                )
            except ConcatTypeError:
                return self.constrain_and_bind_variables(
                    supertype.type_arguments[0],
                    rigid_variables,
                    subtyping_assumptions,
                )
        if isinstance(supertype, Fix):
            return self.constrain_and_bind_variables(
                supertype.unroll(),
                rigid_variables,
                subtyping_assumptions + [(self, supertype)],
            )
        if isinstance(supertype, ForwardTypeReference):
            return self.constrain_and_bind_variables(
                supertype.resolve_forward_references(),
                rigid_variables,
                subtyping_assumptions + [(self, supertype)],
            )
        if isinstance(supertype, Variable):
            if supertype in rigid_variables:
                raise ConcatTypeError(
                    f'{self} is not a subtype of rigid variable {supertype}'
                )
            if not (self.kind <= supertype.kind):
                raise ConcatTypeError(
                    f'{self} has kind {self.kind}, but {supertype} has kind {supertype.kind}'
                )
            return concat.typecheck.Substitutions([(supertype, self)])
        return self._ty.constrain_and_bind_variables(
            supertype, rigid_variables, subtyping_assumptions
        )

    @property
    def kind(self) -> 'Kind':
        return self._ty.kind

    @property
    def brand(self) -> Brand:
        return self._brand

    def __str__(self) -> str:
        return str(self._brand)

    def __repr__(self) -> str:
        return f'NominalType({self._brand!r}, {self._ty!r})'


class ObjectType(IndividualType):
    """Structural record types."""

    def __init__(
        self,
        attributes: Mapping[str, Type],
        _head: Optional['ObjectType'] = None,
    ) -> None:
        super().__init__()

        self._attributes = attributes

        self._head = _head or self

        self._internal_name: Optional[str] = None
        self._internal_name = self._head._internal_name

    @property
    def kind(self) -> 'Kind':
        return IndividualKind

    def apply_substitution(
        self, sub: 'concat.typecheck.Substitutions',
    ) -> 'ObjectType':
        # if no free type vars will be substituted, just return self
        if not any(free_var in sub for free_var in self.free_type_variables()):
            return self

        attributes = cast(
            Dict[str, IndividualType],
            {attr: sub(t) for attr, t in self._attributes.items()},
        )
        subbed_type = type(self)(
            attributes,
            # head is only used to keep track of where a type came from, so
            # there's no need to substitute it
            _head=self._head,
        )
        if self._internal_name is not None:
            subbed_type.set_internal_name(self._internal_name)
        return subbed_type

    def constrain_and_bind_variables(
        self,
        supertype: Type,
        rigid_variables: AbstractSet['Variable'],
        subtyping_assumptions: List[Tuple['Type', 'Type']],
    ) -> 'Substitutions':
        from concat.typecheck import Substitutions

        # every object type is a subtype of object_type
        if (
            self is supertype
            or supertype._type_id == get_object_type()._type_id
            or _contains_assumption(subtyping_assumptions, self, supertype)
        ):
            sub = Substitutions()
            sub.add_subtyping_provenance((self, supertype))
            return sub
        # obj <: `t, `t is not rigid
        # --> `t = obj
        if (
            isinstance(supertype, Variable)
            and supertype.kind >= IndividualKind
            and supertype not in rigid_variables
        ):
            sub = Substitutions([(supertype, self)])
            sub.add_subtyping_provenance((self, supertype))
            return sub
        # obj <: *s? `t...
        # error
        elif isinstance(supertype, (SequenceVariable, TypeSequence)):
            raise ConcatTypeError(
                '{} is an individual type, but {} is a sequence type'.format(
                    self, supertype
                )
            )

        if not (self.kind <= supertype.kind):
            raise ConcatTypeError(
                f'{self} has kind {self.kind}, but {supertype} has kind {supertype.kind}'
            )

        if isinstance(supertype, (StackEffect, PythonFunctionType)):
            sub = self.get_type_of_attribute(
                '__call__'
            ).constrain_and_bind_variables(
                supertype,
                rigid_variables,
                subtyping_assumptions + [(self, supertype)],
            )
            sub.add_subtyping_provenance((self, supertype))
            return sub
        if isinstance(supertype, _OptionalType):
            try:
                sub = self.constrain_and_bind_variables(
                    get_none_type(),
                    rigid_variables,
                    subtyping_assumptions + [(self, supertype)],
                )
                sub.add_subtyping_provenance((self, supertype))
                return sub
            except ConcatTypeError:
                sub = self.constrain_and_bind_variables(
                    supertype.type_arguments[0],
                    rigid_variables,
                    subtyping_assumptions + [(self, supertype)],
                )
                sub.add_subtyping_provenance((self, supertype))
                return sub
        if isinstance(supertype, _NoReturnType):
            raise ConcatTypeError(
                f'No other type, in this case, {self}, is a subtype of {supertype}'
            )
        if isinstance(supertype, Fix):
            unrolled = supertype.unroll()
            sub = self.constrain_and_bind_variables(
                unrolled,
                rigid_variables,
                subtyping_assumptions + [(self, supertype)],
            )
            sub.add_subtyping_provenance((self, supertype))
            return sub
        if isinstance(supertype, ForwardTypeReference):
            resolved = supertype.resolve_forward_references()
            sub = self.constrain_and_bind_variables(
                resolved,
                rigid_variables,
                subtyping_assumptions + [(self, supertype)],
            )
            sub.add_subtyping_provenance((self, supertype))
            return sub
        # Don't forget that there's nominal subtyping too.
        if isinstance(supertype, NominalType):
            raise concat.typecheck.errors.TypeError(
                f'structural type {self} cannot be a subtype of nominal type {supertype}'
            )
        if not isinstance(supertype, ObjectType):
            raise NotImplementedError(repr(supertype))

        subtyping_assumptions = subtyping_assumptions + [(self, supertype)]

        # don't constrain the type arguments, constrain those based on
        # the attributes
        sub = Substitutions()
        for name in supertype._attributes:
            type = self.get_type_of_attribute(name)
            sub = sub(type).constrain_and_bind_variables(
                sub(supertype.get_type_of_attribute(name)),
                rigid_variables,
                subtyping_assumptions,
            )(sub)
        sub.add_subtyping_provenance((self, supertype))
        return sub

    def __repr__(self) -> str:
        head = None if self._head is self else self._head
        return f'{type(self).__qualname__}(attributes={self._attributes!r}, _head={head!r})'

    def _free_type_variables(self) -> InsertionOrderedSet[Variable]:
        ftv = free_type_variables_of_mapping(self.attributes)
        # QUESTION: Include supertypes?
        return ftv

    def __str__(self) -> str:
        if self._internal_name is not None:
            return self._internal_name
        return f'ObjectType({_mapping_to_str(self._attributes)}, {None if self._head is self else self._head})'

    @property
    def attributes(self) -> Mapping[str, Type]:
        return self._attributes

    @property
    def head(self) -> 'ObjectType':
        return self._head


# QUESTION: Should this exist, or should I use ObjectType?
class ClassType(ObjectType):
    """The representation of types of classes, like in "Design and Evaluation of Gradual Typing for Python" (Vitousek et al. 2014)."""

    def constrain_and_bind_variables(
        self, supertype, rigid_variables, subtyping_assumptions
    ) -> 'Substitutions':
        if (
            not supertype.has_attribute('__call__')
            or '__init__' not in self._attributes
        ):
            sub = super().constrain_and_bind_variables(
                supertype, rigid_variables, subtyping_assumptions
            )
            sub.add_subtyping_provenance((self, supertype))
            return sub
        init = self.get_type_of_attribute('__init__')
        while not isinstance(init, (StackEffect, PythonFunctionType)):
            init = init.get_type_of_attribute('__call__')
        bound_init = init.bind()
        sub = bound_init.constrain_and_bind_variables(
            supertype.get_type_of_attribute('__call__'),
            rigid_variables,
            subtyping_assumptions + [(self, supertype)],
        )
        sub.add_subtyping_provenance((self, supertype))
        return sub


class PythonFunctionType(IndividualType):
    def __init__(
        self,
        _overloads: Sequence[Tuple[Type, Type]] = (),
        type_parameters: Sequence[Variable] = (),
        _type_arguments: Sequence[Type] = (),
    ) -> None:
        super().__init__()
        self._arity = len(type_parameters)
        self._type_parameters = type_parameters
        self._type_arguments: Sequence[Type] = []
        self._overloads: Sequence[Tuple[Type, Type]] = []
        if not (
            self._arity == 0
            and len(_type_arguments) == 2
            or self._arity == 2
            and len(_type_arguments) == 0
        ):
            raise ConcatTypeError(
                f'Ill-formed Python function type with arguments {_type_arguments}'
            )
        if self._arity == 0:
            i, o = _type_arguments
            if i.kind != SequenceKind:
                raise ConcatTypeError(
                    f'{i} must be a sequence type, but has kind {i.kind}'
                )
            # HACK: Sequence variables are introduced by the type sequence AST nodes
            if isinstance(i, TypeSequence) and i and i[0].kind == SequenceKind:
                i = TypeSequence(i.as_sequence()[1:])
            _type_arguments = i, o
            if not (o.kind <= ItemKind):
                raise ConcatTypeError(
                    f'{o} must be an item type, but has kind {o.kind}'
                )
            _fixed_overloads: List[Tuple[Type, Type]] = []
            for i, o in _overloads:
                if i.kind != SequenceKind:
                    raise ConcatTypeError(
                        f'{i} must be a sequence type, but has kind {i.kind}'
                    )
                if (
                    isinstance(i, TypeSequence)
                    and i
                    and i[0].kind == SequenceKind
                ):
                    i = TypeSequence(i.as_sequence()[1:])
                if not (o.kind <= ItemKind):
                    raise ConcatTypeError(
                        f'{o} must be an item type, but has kind {o.kind}'
                    )
                _fixed_overloads.append((i, o))
            self._overloads = _fixed_overloads
            self._type_arguments = _type_arguments

    def _free_type_variables(self) -> InsertionOrderedSet[Variable]:
        if self._arity == 0:
            ftv = self.input.free_type_variables()
            ftv |= self.output.free_type_variables()
            return ftv
        else:
            return InsertionOrderedSet([])

    @property
    def kind(self) -> 'Kind':
        if self._arity == 0:
            return IndividualKind
        return GenericTypeKind([SequenceKind, IndividualKind], IndividualKind)

    def __repr__(self) -> str:
        # QUESTION: Is it worth using type(self)?
        return f'{type(self).__qualname__}(_overloads={self._overloads!r}, type_parameters={self._type_parameters!r}, _type_arguments={self._type_arguments})'

    def __str__(self) -> str:
        if not self._type_arguments:
            return 'py_function_type'
        return f'py_function_type[{self.input}, {self.output}]'

    @property
    def attributes(self) -> Mapping[str, Type]:
        return {**super().attributes, '__call__': self}

    def __getitem__(
        self, arguments: Tuple[Type, Type]
    ) -> 'PythonFunctionType':
        if self._arity != 2:
            raise ConcatTypeError(f'{self} is not a generic type')
        if len(arguments) != 2:
            raise ConcatTypeError(
                f'{self} takes two arguments, got {len(arguments)}'
            )
        input = arguments[0]
        output = arguments[1]
        if input.kind != SequenceKind:
            raise ConcatTypeError(
                f'First argument to {self} must be a sequence type of function arguments'
            )
        if not (output.kind <= ItemKind):
            raise ConcatTypeError(
                f'Second argument to {self} (the return type) must be an item type'
            )
        return PythonFunctionType(
            _type_arguments=(input, output), type_parameters=(), _overloads=[],
        )

    def apply_substitution(
        self, sub: 'concat.typecheck.Substitutions'
    ) -> 'PythonFunctionType':
        if self._arity == 0:
            inp = sub(self.input)
            out = sub(self.output)
            overloads: Sequence[Tuple[Type, Type]] = [
                (sub(i), sub(o)) for i, o in self._overloads
            ]
            return PythonFunctionType(
                _type_arguments=(inp, out), _overloads=overloads
            )
        return self

    @property
    def input(self) -> Type:
        assert self._arity == 0
        return self._type_arguments[0]

    @property
    def output(self) -> Type:
        assert self._arity == 0
        return self._type_arguments[1]

    def select_overload(
        self, input_types: Sequence[StackItemType]
    ) -> Tuple['PythonFunctionType', 'Substitutions']:
        for overload in [(self.input, self.output), *self._overloads]:
            try:
                sub = TypeSequence(input_types).constrain_and_bind_variables(
                    overload[0], set(), []
                )
            except TypeError:
                continue
            return (
                sub(py_function_type[overload]),
                sub,
            )
        raise ConcatTypeError(
            'no overload of {} matches types {}'.format(self, input_types)
        )

    def with_overload(self, input: Type, output: Type) -> 'PythonFunctionType':
        return PythonFunctionType(
            _type_arguments=self._type_arguments,
            _overloads=[*self._overloads, (input, output)],
        )

    def bind(self) -> 'PythonFunctionType':
        assert self._arity == 0
        inputs = self.input[1:]
        output = self.output
        overloads = [(i[1:], o) for i, o in self._overloads]
        return PythonFunctionType(
            _type_arguments=[TypeSequence(inputs), output],
            _overloads=overloads,
        )

    def constrain_and_bind_variables(
        self,
        supertype: Type,
        rigid_variables: AbstractSet['Variable'],
        subtyping_assumptions: List[Tuple['Type', 'Type']],
    ) -> 'Substitutions':
        from concat.typecheck import Substitutions

        if self is supertype or _contains_assumption(
            subtyping_assumptions, self, supertype
        ):
            sub = Substitutions()
            sub.add_subtyping_provenance((self, supertype))
            return sub
        if not (self.kind <= supertype.kind):
            raise ConcatTypeError(
                f'{self} has kind {self.kind} but {supertype} has kind {supertype.kind}'
            )
        if self.kind is IndividualKind:
            if supertype is get_object_type():
                sub = Substitutions()
                sub.add_subtyping_provenance((self, supertype))
                return sub
            if (
                isinstance(supertype, ItemVariable)
                and supertype.kind is IndividualKind
                and supertype not in rigid_variables
            ):
                sub = Substitutions([(supertype, self)])
                sub.add_subtyping_provenance((self, supertype))
                return sub
            if isinstance(supertype, _OptionalType):
                sub = self.constrain_and_bind_variables(
                    supertype.type_arguments[0],
                    rigid_variables,
                    subtyping_assumptions,
                )
                sub.add_subtyping_provenance((self, supertype))
                return sub
            if isinstance(supertype, ObjectType) and not supertype.nominal:
                sub = Substitutions()
                for attr in supertype.attributes:
                    self_attr_type = sub(self.get_type_of_attribute(attr))
                    supertype_attr_type = sub(
                        supertype.get_type_of_attribute(attr)
                    )
                    sub = self_attr_type.constrain_and_bind_variables(
                        supertype_attr_type,
                        rigid_variables,
                        subtyping_assumptions,
                    )
                sub.add_subtyping_provenance((self, supertype))
                return sub
            if isinstance(supertype, PythonFunctionType):
                # No need to extend the rigid variables, we know both types have no
                # parameters at this point.

                # Support overloading the subtype.
                exceptions = []
                for overload in [
                    (self.input, self.output),
                    *self._overloads,
                ]:
                    try:
                        subtyping_assumptions_copy = subtyping_assumptions[:]
                        self_input_types = overload[0]
                        supertype_input_types = supertype.input
                        sub = supertype_input_types.constrain_and_bind_variables(
                            self_input_types,
                            rigid_variables,
                            subtyping_assumptions_copy,
                        )
                        sub = sub(self.output).constrain_and_bind_variables(
                            sub(supertype.output),
                            rigid_variables,
                            subtyping_assumptions_copy,
                        )(sub)
                        sub.add_subtyping_provenance((self, supertype))
                        return sub
                    except ConcatTypeError as e:
                        exceptions.append(e)
                    finally:
                        subtyping_assumptions[:] = subtyping_assumptions_copy
                raise ConcatTypeError(
                    'no overload of {} is a subtype of {}'.format(
                        self, supertype
                    )
                ) from exceptions[0]
            raise ConcatTypeError(f'{self} is not a subtype of {supertype}')
        # TODO: Remove generic type responsibility from this class
        if isinstance(supertype, PythonFunctionType) and isinstance(
            supertype.kind, GenericTypeKind
        ):
            sub = Substitutions()
            sub.add_subtyping_provenance((self, supertype))
            return sub


class _PythonOverloadedType(Type):
    def __init__(self) -> None:
        super().__init__()

    def __getitem__(self, args: Sequence[Type]) -> 'PythonFunctionType':
        if len(args) == 0:
            raise ConcatTypeError(
                'py_overloaded must be applied to at least one argument'
            )
        fun_type = args[0]
        if not isinstance(fun_type, PythonFunctionType):
            raise ConcatTypeError(
                'Arguments to py_overloaded must be Python function types'
            )
        for arg in args[1:]:
            if not isinstance(arg, PythonFunctionType):
                raise ConcatTypeError(
                    'Arguments to py_overloaded must be Python function types'
                )
            fun_type = fun_type.with_overload(arg.input, arg.output)
        return fun_type

    @property
    def attributes(self) -> Mapping[str, 'Type']:
        raise ConcatTypeError('py_overloaded does not have attributes')

    def _free_type_variables(self) -> InsertionOrderedSet['Variable']:
        return InsertionOrderedSet([])

    def apply_substitution(
        self, _: 'concat.typecheck.Substitutions'
    ) -> '_PythonOverloadedType':
        return self

    def instantiate(self) -> PythonFunctionType:
        return self[
            py_function_type.instantiate(),
        ]

    def constrain_and_bind_variables(
        self,
        supertype: 'Type',
        rigid_variables: AbstractSet['Variable'],
        subtyping_assumptions: List[Tuple['Type', 'Type']],
    ) -> 'Substitutions':
        raise ConcatTypeError('py_overloaded is a generic type')

    @property
    def kind(self) -> 'Kind':
        return GenericTypeKind([SequenceKind], IndividualKind)

    def __eq__(self, other: object) -> bool:
        return isinstance(other, type(self))


py_overloaded_type = _PythonOverloadedType()


class _NoReturnType(IndividualType):
    def constrain_and_bind_variables(
        self, supertype, rigid_variables, subtyping_assumptions
    ) -> 'Substitutions':
        from concat.typecheck import Substitutions

        return Substitutions()

    def apply_substitution(
        self, sub: 'concat.typecheck.Substitutions'
    ) -> '_NoReturnType':
        return self

    def __repr__(self) -> str:
        return '{}()'.format(type(self).__qualname__)

    def _free_type_variables(self) -> InsertionOrderedSet['Variable']:
        return InsertionOrderedSet([])


class _OptionalType(IndividualType):
    def __init__(self, type_argument: Type) -> None:
        super().__init__()
        if not (type_argument.kind <= ItemKind):
            raise ConcatTypeError(
                f'{type_argument} must be an item type, but has kind {type_argument.kind}'
            )
        while isinstance(type_argument, _OptionalType):
            type_argument = type_argument._type_argument
        self._type_argument: Type = type_argument

    def __repr__(self) -> str:
        return f'{type(self).__qualname__}({self._type_argument!r})'

    def __str__(self) -> str:
        return f'optional_type[{self._type_argument}]'

    def _free_type_variables(self) -> InsertionOrderedSet[Variable]:
        return self._type_argument.free_type_variables()

    def __eq__(self, other: object) -> bool:
        if isinstance(other, _OptionalType):
            return self._type_argument == other._type_argument
        return super().__eq__(other)

    def constrain_and_bind_variables(
        self, supertype, rigid_variables, subtyping_assumptions
    ) -> 'Substitutions':
        from concat.typecheck import Substitutions

        if (
            self is supertype
            or _contains_assumption(subtyping_assumptions, self, supertype)
            or supertype is get_object_type()
        ):
            return Substitutions()
        # A special case for better resuls (I think)
        if isinstance(supertype, _OptionalType):
            return self._type_argument.constrain_and_bind_variables(
                supertype._type_argument,
                rigid_variables,
                subtyping_assumptions,
            )
        if self.kind != supertype.kind:
            raise ConcatTypeError(
                f'{self} is an individual type, but {supertype} has kind {supertype.kind}'
            )
        # FIXME: optional[none] should simplify to none
        if (
            self._type_argument is get_none_type()
            and supertype is get_none_type()
        ):
            return Substitutions()

        sub = get_none_type().constrain_and_bind_variables(
            supertype, rigid_variables, subtyping_assumptions
        )
        sub = sub(self._type_argument).constrain_and_bind_variables(
            sub(supertype), rigid_variables, subtyping_assumptions
        )
        return sub

    def apply_substitution(
        self, sub: 'concat.typecheck.Substitutions'
    ) -> '_OptionalType':
        return _OptionalType(sub(self._type_argument))

    @property
    def type_arguments(self) -> Sequence[Type]:
        return [self._type_argument]


# FIXME: Not a total order, using total_ordering might be very unsound.
@functools.total_ordering
class Kind(abc.ABC):
    @abc.abstractmethod
    def __eq__(self, other: object) -> bool:
        pass

    @abc.abstractmethod
    def __lt__(self, other: 'Kind') -> bool:
        pass

    @abc.abstractmethod
    def __str__(self) -> str:
        pass


class _ItemKind(Kind):
    __instance: Optional['_ItemKind'] = None

    def __new__(cls) -> '_ItemKind':
        if cls.__instance is None:
            cls.__instance = super().__new__(cls)
        return cls.__instance

    def __eq__(self, other: object) -> bool:
        return self is other

    def __lt__(self, other: Kind) -> bool:
        return False

    def __str__(self) -> str:
        return 'Item'


ItemKind = _ItemKind()


class _IndividualKind(Kind):
    __instance: Optional['_IndividualKind'] = None

    def __new__(cls) -> '_IndividualKind':
        if cls.__instance is None:
            cls.__instance = super().__new__(cls)
        return cls.__instance

    def __eq__(self, other: object) -> bool:
        return self is other

    def __lt__(self, other: Kind) -> bool:
        return other is ItemKind

    def __str__(self) -> str:
        return 'Individual'


IndividualKind = _IndividualKind()


class _SequenceKind(Kind):
    __instance: Optional['_SequenceKind'] = None

    def __new__(cls) -> '_SequenceKind':
        if cls.__instance is None:
            cls.__instance = super().__new__(cls)
        return cls.__instance

    def __eq__(self, other: object) -> bool:
        return self is other

    def __lt__(self, other: Kind) -> bool:
        return other is ItemKind

    def __str__(self) -> str:
        return 'Sequence'


SequenceKind = _SequenceKind()


class GenericTypeKind(Kind):
    def __init__(
        self, parameter_kinds: Sequence[Kind], result_kind: Kind
    ) -> None:
        if not parameter_kinds:
            raise ConcatTypeError(
                'Generic type kinds cannot have empty parameters'
            )
        self.parameter_kinds = parameter_kinds
        self.result_kind = result_kind

    def __eq__(self, other: object) -> bool:
        return (
            isinstance(other, GenericTypeKind)
            and list(self.parameter_kinds) == list(other.parameter_kinds)
            and self.result_kind == other.result_kind
        )

    def __lt__(self, other: Kind) -> bool:
        if not isinstance(other, Kind):
            return NotImplemented
        if other is ItemKind:
            return True
        if not isinstance(other, GenericTypeKind):
            return False
        if len(self.parameter_kinds) != len(other.parameter_kinds):
            return False
        return (
            list(self.parameter_kinds) > list(other.parameter_kinds)
            and self.result_kind < other.result_kind
        )

    def __str__(self) -> str:
        return f'Generic[{", ".join(map(str, self.parameter_kinds))}, {self.result_kind}]'


class Fix(Type):
    def __init__(self, var: Variable, body: Type) -> None:
        super().__init__()
        assert var.kind == body.kind
        self._var = var
        self._body = body
        self._unrolled_ty: Optional[Type] = None
        self._cache: Dict[int, Type] = {}

    def __repr__(self) -> str:
        return f'Fix({self._var!r}, {self._body!r})'

    def __str__(self) -> str:
        if self._internal_name is not None:
            return self._internal_name
        return f'Fix({self._var}, {self._body})'

    def _apply(self, t: Type) -> Type:
        from concat.typecheck import Substitutions

        if t._type_id not in self._cache:
            sub = Substitutions([(self._var, t)])
            self._cache[t._type_id] = sub(self._body)
            assert (
                self._var not in self._cache[t._type_id].free_type_variables()
            )
        return self._cache[t._type_id]

    def unroll(self) -> Type:
        if self._unrolled_ty is None:
            self._unrolled_ty = self._apply(self)
            if self._internal_name is not None:
                self._unrolled_ty.set_internal_name(self._internal_name)
            # self._unrolled_ty._type_id = self._type_id
        return self._unrolled_ty

    def _free_type_variables(self) -> InsertionOrderedSet[Variable]:
        return self._body.free_type_variables() - {self._var}

    def apply_substitution(self, sub: 'Substitutions') -> Type:
        from concat.typecheck import Substitutions

        if all(v not in self.free_type_variables() for v in sub):
            return self
        sub = Substitutions(
            {v: t for v, t in sub.items() if v is not self._var}
        )

        return Fix(self._var, sub(self._body))

    @property
    def attributes(self) -> Mapping[str, Type]:
        return self.unroll().attributes

    def constrain_and_bind_variables(
        self, supertype, rigid_variables, subtyping_assumptions
    ) -> 'Substitutions':
        from concat.typecheck import Substitutions

        if supertype._type_id == get_object_type()._type_id or _contains_assumption(
            subtyping_assumptions, self, supertype
        ):
            sub = Substitutions()
            sub.add_subtyping_provenance((self, supertype))
            return sub

        if isinstance(supertype, Fix):
            unrolled = supertype.unroll()
            # BUG: The unrolled types have the same type ids, so the assumption
            # is used immediately, which is unsound.
            sub = self.unroll().constrain_and_bind_variables(
                unrolled,
                rigid_variables,
                subtyping_assumptions + [(self, supertype)],
            )
            sub.add_subtyping_provenance((self, supertype))
            return sub

        sub = self.unroll().constrain_and_bind_variables(
            supertype,
            rigid_variables,
            subtyping_assumptions + [(self, supertype)],
        )
        sub.add_subtyping_provenance((self, supertype))
        return sub

    @property
    def kind(self) -> Kind:
        return self._var.kind

    def __getitem__(self, args: Any) -> Any:
        return self.unroll()[args]


class ForwardTypeReference(Type):
    def __init__(
        self,
        kind: Kind,
        name_to_resolve: str,
        resolution_env: 'Environment',
        _type_arguments: TypeArguments = (),
    ) -> None:
        super().__init__()
        self._kind = kind
        self._name_to_resolve = name_to_resolve
        self._resolution_env = resolution_env
        self._resolved_type: Optional[Type] = None
        self._type_arguments = _type_arguments

    def _resolve(self) -> Type:
        ty = self._resolution_env[self._name_to_resolve]
        if self._type_arguments:
            ty = ty[self._type_arguments]
        return ty

    def _as_hashable_tuple(self) -> tuple:
        return (
            self._kind,
            id(self._resolution_env),
            self._name_to_resolve,
            tuple(self._type_arguments),
        )

    def __getitem__(self, args: TypeArguments) -> Type:
        if self._resolved_type is not None:
            return self._resolved_type[args]

        if isinstance(self.kind, GenericTypeKind):
            if len(self.kind.parameter_kinds) != len(args):
                raise ConcatTypeError(
                    'Wrong number of arguments to generic type'
                )
            for kind, arg in zip(self.kind.parameter_kinds, args):
                if kind != arg.kind:
                    raise ConcatTypeError(
                        f'Type argument has kind {arg.kind}, expected kind {kind}'
                    )
            return ForwardTypeReference(
                IndividualKind,
                self._name_to_resolve,
                self._resolution_env,
                _type_arguments=args,
            )
        raise ConcatTypeError(f'{self} is not a generic type')

    def resolve_forward_references(self) -> Type:
        if self._resolved_type is None:
            self._resolved_type = self._resolve()
        return self._resolved_type

    def apply_substitution(
        self, sub: 'concat.typecheck.Substitutions'
    ) -> Type:
        if self._resolved_type is not None:
            return sub(self._resolved_type)

        return self

    @property
    def attributes(self) -> Mapping[str, Type]:
        if self._resolved_type is not None:
            return self._resolved_type.attributes

        raise ConcatTypeError(
            'Cannot access attributes of type before they are defined'
        )

    def constrain_and_bind_variables(
        self,
        supertype: Type,
        rigid_variables: AbstractSet['Variable'],
        subtyping_assumptions: List[Tuple['Type', 'Type']],
    ) -> 'Substitutions':
        if self is supertype or _contains_assumption(
            subtyping_assumptions, self, supertype
        ):
            return concat.typecheck.Substitutions()

        return self.resolve_forward_references().constrain_and_bind_variables(
            supertype,
            rigid_variables,
            subtyping_assumptions + [(self, supertype)],
        )

    def _free_type_variables(self) -> InsertionOrderedSet[Variable]:
        return InsertionOrderedSet([])

    @property
    def kind(self) -> Kind:
        return self._kind


def _iterable_to_str(iterable: Iterable) -> str:
    return '[' + ', '.join(map(str, iterable)) + ']'


def _mapping_to_str(mapping: Mapping) -> str:
    return (
        '{'
        + ', '.join(
            '{}: {}'.format(key, value) for key, value in mapping.items()
        )
        + '}'
    )


# expose _Function as StackEffect
StackEffect = _Function

_x = BoundVariable(kind=IndividualKind)

float_type = NominalType(Brand('float', IndividualKind, []), ObjectType({}))
no_return_type = _NoReturnType()


_object_type: Optional[Type] = None


def get_object_type() -> Type:
    assert _object_type is not None
    return _object_type


def set_object_type(ty: Type) -> None:
    global _object_type
    assert _object_type is None
    _object_type = ty


_list_type: Optional[Type] = None


def get_list_type() -> Type:
    assert _list_type is not None
    return _list_type


def set_list_type(ty: Type) -> None:
    global _list_type
    _list_type = ty


_str_type: Optional[Type] = None


def get_str_type() -> Type:
    assert _str_type is not None
    return _str_type


def set_str_type(ty: Type) -> None:
    global _str_type
    _str_type = ty


_tuple_type: Optional[Type] = None


def get_tuple_type() -> Type:
    assert _tuple_type is not None
    return _tuple_type


def set_tuple_type(ty: Type) -> None:
    global _tuple_type
    _tuple_type = ty


_int_type: Optional[Type] = None


def get_int_type() -> Type:
    assert _int_type is not None
    return _int_type


def set_int_type(ty: Type) -> None:
    global _int_type
    _int_type = ty


_bool_type: Optional[Type] = None


def get_bool_type() -> Type:
    assert _bool_type is not None
    return _bool_type


def set_bool_type(ty: Type) -> None:
    global _bool_type
    _bool_type = ty


_none_type: Optional[Type] = None


def get_none_type() -> Type:
    assert _none_type is not None
    return _none_type


def set_none_type(ty: Type) -> None:
    global _none_type
    _none_type = ty


_module_type: Optional[Type] = None


def get_module_type() -> Type:
    assert _module_type is not None
    return _module_type


def set_module_type(ty: Type) -> None:
    global _module_type
    _module_type = ty


_arg_type_var = SequenceVariable()
_return_type_var = ItemVariable(IndividualKind)
py_function_type = PythonFunctionType(
    type_parameters=[_arg_type_var, _return_type_var]
)
py_function_type.set_internal_name('py_function_type')

_invert_result_var = ItemVariable(IndividualKind)
invertible_type = GenericType(
    [_invert_result_var],
    ObjectType(
        {'__invert__': py_function_type[TypeSequence([]), _invert_result_var]},
    ),
)

_sub_operand_type = BoundVariable(ItemKind)
_sub_result_type = BoundVariable(ItemKind)
# FIXME: Add reverse_substractable_type for __rsub__
subtractable_type = GenericType(
    [_sub_operand_type, _sub_result_type],
    ObjectType(
        {
            '__sub__': py_function_type[
                TypeSequence([_sub_operand_type]), _sub_result_type
            ]
        },
    ),
)
subtractable_type.set_internal_name('subtractable_type')

_add_other_operand_type = BoundVariable(ItemKind)
_add_result_type = BoundVariable(ItemKind)

addable_type = GenericType(
    [_add_other_operand_type, _add_result_type],
    ObjectType(
        {
            '__add__': py_function_type[
                # QUESTION: Should methods include self?
                TypeSequence([_add_other_operand_type]),
                _add_result_type,
            ]
        },
    ),
)
addable_type.set_internal_name('addable_type')

# NOTE: Allow comparison methods to return any object. I don't think Python
# stops it. Plus, these definitions don't have to depend on bool, which is
# defined in builtins.cati.

_other_type = BoundVariable(ItemKind)
_return_type = BoundVariable(ItemKind)
geq_comparable_type = GenericType(
    [_other_type, _return_type],
    ObjectType(
        {
            '__ge__': py_function_type[
                TypeSequence([_other_type]), _return_type
            ]
        },
    ),
)
geq_comparable_type.set_internal_name('geq_comparable_type')

leq_comparable_type = GenericType(
    [_other_type, _return_type],
    ObjectType(
        {
            '__le__': py_function_type[
                TypeSequence([_other_type]), _return_type
            ]
        },
    ),
)
leq_comparable_type.set_internal_name('leq_comparable_type')

lt_comparable_type = GenericType(
    [_other_type, _return_type],
    ObjectType(
        {
            '__lt__': py_function_type[
                TypeSequence([_other_type]), _return_type
            ]
        },
    ),
)
lt_comparable_type.set_internal_name('lt_comparable_type')

_result_type = BoundVariable(ItemKind)

iterator_type = GenericType(
    [_result_type],
    Fix(
        _x,
        ObjectType(
            {
                '__iter__': py_function_type[TypeSequence([]), _x],
                '__next__': py_function_type[TypeSequence([]), _result_type],
            },
        ),
    ),
)
iterator_type.set_internal_name('iterator_type')

iterable_type = GenericType(
    [_result_type],
    ObjectType(
        {
            '__iter__': py_function_type[
                TypeSequence([]), iterator_type[_result_type,]
            ]
        },
    ),
)
iterable_type.set_internal_name('iterable_type')

context_manager_type = ObjectType(
    {
        # TODO: Add argument and return types. I think I'll need a special
        # py_function representation for that.
        '__enter__': py_function_type,
        '__exit__': py_function_type,
    },
)
context_manager_type.set_internal_name('context_manager_type')

_optional_type_var = BoundVariable(ItemKind)
optional_type = GenericType(
    [_optional_type_var], _OptionalType(_optional_type_var)
)
optional_type.set_internal_name('optional_type')

_index_type_var = BoundVariable(ItemKind)
_result_type_var = BoundVariable(ItemKind)
subscriptable_type = GenericType(
    [_index_type_var, _result_type_var],
    ObjectType(
        {
            '__getitem__': py_function_type[
                TypeSequence([_index_type_var]), _result_type_var
            ],
        },
    ),
)
