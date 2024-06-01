from concat.orderedset import InsertionOrderedSet
import concat.typecheck
from typing import (
    AbstractSet,
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
from typing_extensions import Literal, Self
import abc
import collections.abc


if TYPE_CHECKING:
    from concat.typecheck import Environment, Substitutions


class Type(abc.ABC):
    def __init__(self) -> None:
        self._free_type_variables_cached: Optional[
            InsertionOrderedSet[_Variable]
        ] = None
        self._internal_name: Optional[str] = None
        self._forward_references_resolved = False

    # QUESTION: Do I need this?
    def is_subtype_of(self, supertype: 'Type') -> bool:
        try:
            sub = self.constrain_and_bind_variables(supertype, set(), [])
        except concat.typecheck.TypeError:
            return False
        return not sub

    # No <= implementation using subtyping, because variables overload that for
    # sort by identity.

    def __eq__(self, other: object) -> bool:
        if self is other:
            return True
        if not isinstance(other, Type):
            return NotImplemented
        # QUESTION: Define == separately from is_subtype_of?
        return self.is_subtype_of(other) and other.is_subtype_of(self)

    def get_type_of_attribute(self, name: str) -> 'Type':
        raise AttributeError(self, name)

    def has_attribute(self, name: str) -> bool:
        try:
            self.get_type_of_attribute(name)
            return True
        except AttributeError:
            return False

    @abc.abstractproperty
    def attributes(self) -> Mapping[str, 'Type']:
        pass

    @abc.abstractmethod
    def _free_type_variables(self) -> InsertionOrderedSet['_Variable']:
        pass

    def free_type_variables(self) -> InsertionOrderedSet['_Variable']:
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
        rigid_variables: AbstractSet['_Variable'],
        subtyping_assumptions: List[Tuple['IndividualType', 'IndividualType']],
    ) -> 'Substitutions':
        raise NotImplementedError

    # QUESTION: Should I remove this? Should I not distinguish between subtype
    # and supertype variables in the other two constraint methods? I should
    # look bidirectional typing with polymorphism/generics. Maybe 'Complete and
    # Easy'?
    def constrain(self, supertype: 'Type') -> None:
        if not self.is_subtype_of(supertype):
            raise concat.typecheck.TypeError(
                '{} is not a subtype of {}'.format(self, supertype)
            )

    def instantiate(self) -> 'Type':
        return self

    @abc.abstractmethod
    def resolve_forward_references(self) -> Self:
        self._forward_references_resolved = True
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


class GenericType(Type):
    def __init__(
        self,
        type_parameters: Sequence['_Variable'],
        body: Type,
        is_variadic: bool = False,
    ) -> None:
        super().__init__()
        assert type_parameters
        self._type_parameters = type_parameters
        if body.kind != IndividualKind():
            raise concat.typecheck.TypeError(
                f'Cannot be polymorphic over non-individual type {body}'
            )
        self._body = body
        self._instantiations: Dict[Tuple[Type, ...], Type] = {}
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

        type_arguments = tuple(type_arguments)
        if type_arguments in self._instantiations:
            return self._instantiations[type_arguments]
        expected_kinds = [var.kind for var in self._type_parameters]
        actual_kinds = [ty.kind for ty in type_arguments]
        if expected_kinds != actual_kinds:
            raise concat.typecheck.TypeError(
                f'A type argument to {self} has the wrong kind, type arguments: {type_arguments}, expected kinds: {expected_kinds}'
            )
        sub = Substitutions(zip(self._type_parameters, type_arguments))
        instance = sub(self._body)
        self._instantiations[type_arguments] = instance
        if self._internal_name is not None:
            instance_internal_name = self._internal_name
            instance_internal_name += (
                '[' + ', '.join(map(str, type_arguments)) + ']'
            )
            instance.set_internal_name(instance_internal_name)
        return instance

    @property
    def kind(self) -> 'Kind':
        kinds = [var.kind for var in self._type_parameters]
        return GenericTypeKind(kinds)

    def resolve_forward_references(self) -> 'GenericType':
        self._body = self._body.resolve_forward_references()
        return self

    def instantiate(self) -> Type:
        fresh_vars: Sequence[_Variable] = [
            type(var)() for var in self._type_parameters
        ]
        return self[fresh_vars]

    def constrain_and_bind_variables(
        self,
        supertype: 'Type',
        rigid_variables: AbstractSet['_Variable'],
        subtyping_assumptions: List[Tuple['IndividualType', 'IndividualType']],
    ) -> 'Substitutions':
        from concat.typecheck import Substitutions

        if self is supertype or _contains_assumption(
            subtyping_assumptions, self, supertype
        ):
            return Substitutions([])
        if self.kind != supertype.kind:
            raise concat.typecheck.TypeError(
                f'{self} has kind {self.kind} but {supertype} has kind {supertype.kind}'
            )
        if not isinstance(supertype, GenericType):
            raise NotImplementedError(supertype)
        shared_vars = [type(var)() for var in self._type_parameters]
        self_instance = self[shared_vars]
        supertype_instance = supertype[shared_vars]
        rigid_variables = (
            rigid_variables
            | set(self._type_parameters)
            | set(supertype._type_parameters)
        )
        return self_instance.constrain_and_bind_variables(
            supertype_instance, rigid_variables, subtyping_assumptions
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
        ty = GenericType(self._type_parameters, sub(self._body))
        return ty

    @property
    def attributes(self) -> NoReturn:
        raise concat.typecheck.TypeError(
            'Generic types do not have attributes; maybe you forgot type arguments?'
        )

    def _free_type_variables(self) -> InsertionOrderedSet['_Variable']:
        return self._body.free_type_variables() - set(self._type_parameters)


class IndividualType(Type, abc.ABC):
    def instantiate(self) -> 'IndividualType':
        return cast(IndividualType, super().instantiate())

    @abc.abstractmethod
    def apply_substitution(
        self, sub: 'concat.typecheck.Substitutions',
    ) -> 'IndividualType':
        pass

    @property
    def kind(self) -> 'Kind':
        return IndividualKind()

    @property
    def attributes(self) -> Mapping[str, Type]:
        return {}


class _Variable(Type, abc.ABC):
    """Objects that represent type variables.

    Every type variable object is assumed to be unique. Thus, fresh type
    variables can be made simply by creating new objects. They can also be
    compared by identity."""

    def apply_substitution(
        self, sub: 'concat.typecheck.Substitutions'
    ) -> Union[IndividualType, '_Variable', 'TypeSequence']:
        if self in sub:
            result = sub[self]
            assert self.kind == result.kind, f'{self!r} --> {result!r}'
            return result  # type: ignore
        return self

    def _free_type_variables(self) -> InsertionOrderedSet['_Variable']:
        return InsertionOrderedSet([self])

    def __lt__(self, other) -> bool:
        """Comparator for storing variables in OrderedSets."""
        return id(self) < id(other)

    def __gt__(self, other) -> bool:
        """Comparator for storing variables in OrderedSets."""
        return id(self) > id(other)

    def __eq__(self, other) -> bool:
        return id(self) == id(other)


class IndividualVariable(_Variable, IndividualType):
    def __init__(self) -> None:
        super().__init__()

    def constrain_and_bind_variables(
        self,
        supertype: Type,
        rigid_variables: AbstractSet['_Variable'],
        subtyping_assumptions: List[Tuple[IndividualType, IndividualType]],
    ) -> 'Substitutions':
        from concat.typecheck import Substitutions

        if self is supertype:
            return Substitutions()
        if supertype.kind != IndividualKind():
            raise concat.typecheck.TypeError(
                '{} must be an individual type: expected {}'.format(
                    supertype, self
                )
            )
        mapping: Mapping[_Variable, Type]
        if (
            isinstance(supertype, IndividualVariable)
            and supertype not in rigid_variables
        ):
            mapping = {supertype: self}
            return Substitutions(mapping)
        if isinstance(supertype, _OptionalType):
            try:
                return self.constrain_and_bind_variables(
                    supertype.type_arguments[0],
                    rigid_variables,
                    subtyping_assumptions,
                )
            except concat.typecheck.TypeError:
                return self.constrain_and_bind_variables(
                    none_type, rigid_variables, subtyping_assumptions
                )
        if self in rigid_variables:
            raise concat.typecheck.TypeError(
                f'{self} is considered fixed here and cannot become a subtype of {supertype}'
            )
        mapping = {self: supertype}
        return Substitutions(mapping)

    # __hash__ by object identity is used since that's the only way for two
    # type variables to be ==.
    def __hash__(self) -> int:
        return hash(id(self))

    def __str__(self) -> str:
        return '`t_{}'.format(id(self))

    def __repr__(self) -> str:
        return '<individual variable {}>'.format(id(self))

    def apply_substitution(
        self, sub: 'concat.typecheck.Substitutions'
    ) -> IndividualType:
        return cast(IndividualType, super().apply_substitution(sub))

    @property
    def attributes(self) -> NoReturn:
        raise concat.typecheck.TypeError(
            '{} is an individual type variable, so its attributes are unknown'.format(
                self
            )
        )

    def resolve_forward_references(self) -> 'IndividualVariable':
        return self

    @property
    def kind(self) -> 'Kind':
        return IndividualKind()


class SequenceVariable(_Variable):
    def __init__(self) -> None:
        super().__init__()

    def __str__(self) -> str:
        return '*t_{}'.format(id(self))

    def __hash__(self) -> int:
        return hash(id(self))

    def constrain_and_bind_variables(
        self,
        supertype: Type,
        rigid_variables: AbstractSet['_Variable'],
        subtyping_assumptions: List[Tuple['IndividualType', 'IndividualType']],
    ) -> 'Substitutions':
        from concat.typecheck import Substitutions

        if not isinstance(supertype, (SequenceVariable, TypeSequence)):
            raise concat.typecheck.TypeError(
                '{} must be a sequence type, not {}'.format(self, supertype)
            )
        if self in rigid_variables:
            raise concat.typecheck.TypeError(
                '{} is fixed here and cannot become a subtype of another type'.format(
                    self
                )
            )
        # occurs check
        if self is not supertype and self in supertype.free_type_variables():
            raise concat.typecheck.TypeError(
                '{} cannot be a subtype of {} because it appears in {}'.format(
                    self, supertype, supertype
                )
            )
        if isinstance(supertype, SequenceVariable):
            return Substitutions([(supertype, self)])
        return Substitutions([(self, supertype)])

    def get_type_of_attribute(self, name: str) -> NoReturn:
        raise concat.typecheck.TypeError(
            'the sequence type {} does not hold attributes'.format(self)
        )

    @property
    def attributes(self) -> NoReturn:
        raise concat.typecheck.TypeError(
            'the sequence type {} does not hold attributes'.format(self)
        )

    def resolve_forward_references(self) -> 'SequenceVariable':
        return self

    @property
    def kind(self) -> 'Kind':
        return SequenceKind()


class TypeSequence(Type, Iterable['StackItemType']):
    def __init__(self, sequence: Sequence['StackItemType']) -> None:
        super().__init__()
        self._rest: Optional[SequenceVariable]
        if sequence and isinstance(sequence[0], SequenceVariable):
            self._rest = sequence[0]
            self._individual_types = sequence[1:]
        else:
            self._rest = None
            self._individual_types = sequence

    def as_sequence(self) -> Sequence['StackItemType']:
        if self._rest is not None:
            return [self._rest, *self._individual_types]
        return self._individual_types

    def apply_substitution(self, sub) -> 'TypeSequence':
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
        rigid_variables: AbstractSet['_Variable'],
        subtyping_assumptions: List[Tuple['IndividualType', 'IndividualType']],
    ) -> 'Substitutions':
        """Check that self is a subtype of supertype.

        Free type variables that appear in either type sequence are set to be
        equal to their counterparts in the other sequence so that type
        information can be propagated into calls of named functions.
        """
        from concat.typecheck import Substitutions

        if _contains_assumption(subtyping_assumptions, self, supertype):
            return Substitutions()

        if isinstance(supertype, SequenceVariable):
            supertype = TypeSequence([supertype])

        if isinstance(supertype, TypeSequence):
            if self._is_empty():
                # [] <: []
                if supertype._is_empty():
                    return Substitutions()
                # [] <: *a, *a is not rigid
                # --> *a = []
                elif (
                    self._is_empty()
                    and supertype._rest
                    and not supertype._individual_types
                    and supertype._rest not in rigid_variables
                ):
                    return Substitutions([(supertype._rest, self)])
                # [] <: *a? `t0 `t...
                # error
                else:
                    raise concat.typecheck.StackMismatchError(self, supertype)
            elif not self._individual_types:
                # *a <: [], *a is not rigid
                # --> *a = []
                if supertype._is_empty() and self._rest not in rigid_variables:
                    assert self._rest is not None
                    return Substitutions([(self._rest, supertype)])
                # *a <: *a
                if (
                    self._rest is supertype._rest
                    and not supertype._individual_types
                ):
                    return Substitutions()
                # *a <: *b? `t..., *a is not rigid, *a is not free in RHS
                # --> *a = RHS
                if (
                    self._rest
                    and self._rest not in rigid_variables
                    and self._rest not in supertype.free_type_variables()
                ):
                    return Substitutions([(self._rest, supertype)])
                else:
                    raise concat.typecheck.StackMismatchError(self, supertype)
            else:
                # *a? `t... `t_n <: []
                # error
                if supertype._is_empty():
                    raise concat.typecheck.StackMismatchError(self, supertype)
                # *a? `t... `t_n <: *b, *b is not rigid, *b is not free in LHS
                # --> *b = LHS
                elif (
                    not supertype._individual_types
                    and supertype._rest
                    and supertype._rest not in self.free_type_variables()
                    and supertype._rest not in rigid_variables
                ):
                    return Substitutions([(supertype._rest, self)])
                # `t_n <: `s_m  *a? `t... <: *b? `s...
                #   ---
                # *a? `t... `t_n <: *b? `s... `s_m
                elif supertype._individual_types:
                    sub = self._individual_types[
                        -1
                    ].constrain_and_bind_variables(
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
                    except concat.typecheck.StackMismatchError:
                        # TODO: Add info about occurs check and rigid variables.
                        raise concat.typecheck.StackMismatchError(
                            self, supertype
                        )
                else:
                    raise concat.typecheck.StackMismatchError(self, supertype)
        else:
            raise concat.typecheck.TypeError(
                f'{self} is a sequence type, not {supertype}'
            )

    def _free_type_variables(self) -> InsertionOrderedSet['_Variable']:
        ftv: InsertionOrderedSet[_Variable] = InsertionOrderedSet([])
        for t in self:
            ftv |= t.free_type_variables()
        return ftv

    @property
    def attributes(self) -> NoReturn:
        raise concat.typecheck.TypeError(
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

    def __getitem__(
        self, key: Union[int, slice]
    ) -> Union['StackItemType', 'TypeSequence']:
        if isinstance(key, int):
            return self.as_sequence()[key]
        return TypeSequence(self.as_sequence()[key])

    def __str__(self) -> str:
        return '[' + ', '.join(str(t) for t in self) + ']'

    def __repr__(self) -> str:
        return 'TypeSequence([' + ', '.join(repr(t) for t in self) + '])'

    def __iter__(self) -> Iterator['StackItemType']:
        return iter(self.as_sequence())

    def __hash__(self) -> int:
        return hash(tuple(self.as_sequence()))

    def resolve_forward_references(self) -> 'TypeSequence':
        self._individual_types = [
            t.resolve_forward_references() for t in self._individual_types
        ]
        return self

    @property
    def kind(self) -> 'Kind':
        return SequenceKind()


# TODO: Rename to StackEffect at all use sites.
class _Function(IndividualType):
    def __init__(
        self, input_types: TypeSequence, output_types: TypeSequence,
    ) -> None:
        for ty in input_types[1:]:
            if ty.kind != IndividualKind():
                raise concat.typecheck.TypeError(
                    f'{ty} must be an individual type'
                )
        for ty in output_types[1:]:
            if ty.kind != IndividualKind():
                raise concat.typecheck.TypeError(
                    f'{ty} must be an individual type'
                )
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

    def __hash__(self) -> int:
        # FIXME: Alpha equivalence
        return hash((self.input, self.output))

    def constrain_and_bind_variables(
        self,
        supertype: Type,
        rigid_variables: AbstractSet['_Variable'],
        subtyping_assumptions: List[Tuple[IndividualType, IndividualType]],
    ) -> 'Substitutions':
        from concat.typecheck import Substitutions

        if (
            self is supertype
            or _contains_assumption(subtyping_assumptions, self, supertype)
            or supertype is get_object_type()
        ):
            return Substitutions()

        if (
            isinstance(supertype, IndividualVariable)
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
            raise concat.typecheck.TypeError(
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

    def _free_type_variables(self) -> InsertionOrderedSet['_Variable']:
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

    def get_type_of_attribute(self, name: str) -> '_Function':
        if name == '__call__':
            return self
        raise AttributeError(self, name)

    @property
    def attributes(self) -> Mapping[str, 'StackEffect']:
        return {'__call__': self}

    def apply_substitution(
        self, sub: 'concat.typecheck.Substitutions'
    ) -> '_Function':
        return _Function(sub(self.input), sub(self.output))

    def bind(self) -> '_Function':
        return _Function(self.input[:-1], self.output)

    def resolve_forward_references(self) -> 'StackEffect':
        self.input = self.input.resolve_forward_references()
        self.output = self.output.resolve_forward_references()
        return self


class QuotationType(_Function):
    def __init__(self, fun_type: _Function) -> None:
        super().__init__(fun_type.input, fun_type.output)

    def constrain_and_bind_variables(
        self,
        supertype: Type,
        rigid_variables: AbstractSet['_Variable'],
        subtyping_assumptions: List[Tuple[IndividualType, IndividualType]],
    ) -> 'Substitutions':
        if (
            isinstance(supertype, ObjectType)
            and supertype.head == iterable_type
        ):
            # FIXME: Don't present new variables every time.
            # FIXME: Account for the types of the elements of the quotation.
            in_var = IndividualVariable()
            out_var = IndividualVariable()
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
) -> InsertionOrderedSet[_Variable]:
    ftv: InsertionOrderedSet[_Variable] = InsertionOrderedSet([])
    for sigma in attributes.values():
        ftv |= sigma.free_type_variables()
    return ftv


TypeArguments = Sequence[Type]
_T = TypeVar('_T')


def _contains_assumption(
    assumptions: Sequence[Tuple[Type, Type]], subtype: Type, supertype: Type
) -> bool:
    for sub, sup in assumptions:
        if sub is subtype and sup is supertype:
            return True
    return False


class ObjectType(IndividualType):
    """The representation of types of objects, based on a gradual typing paper.

    That paper is "Design and Evaluation of Gradual Typing for Python"
    (Vitousek et al. 2014)."""

    def __init__(
        self,
        self_type: IndividualVariable,
        attributes: Mapping[str, Type],
        nominal_supertypes: Sequence[IndividualType] = (),
        nominal: bool = False,
        _head: Optional['ObjectType'] = None,
    ) -> None:
        assert isinstance(self_type, IndividualVariable)
        super().__init__()
        # There should be no need to make the self_type variable unique because
        # it is treated as a bound variable in apply_substitution. In other
        # words, it is removed from any substitution received.
        self._self_type = self_type

        self._attributes = attributes

        self._nominal_supertypes = nominal_supertypes
        self._nominal = nominal

        self._head = _head or self

        self._internal_name: Optional[str] = None
        self._internal_name = self._head._internal_name

    @property
    def nominal(self) -> bool:
        return self._nominal

    def resolve_forward_references(self) -> 'ObjectType':
        self._attributes = {
            attr: t.resolve_forward_references()
            for attr, t in self._attributes.items()
        }
        self._nominal_supertypes = [
            t.resolve_forward_references() for t in self._nominal_supertypes
        ]
        return self

    @property
    def kind(self) -> 'Kind':
        return IndividualKind()

    def apply_substitution(
        self, sub: 'concat.typecheck.Substitutions',
    ) -> 'ObjectType':
        from concat.typecheck import Substitutions

        sub = Substitutions(
            {a: i for a, i in sub.items() if a is not self._self_type}
        )
        # if no free type vars will be substituted, just return self
        if not any(free_var in sub for free_var in self.free_type_variables()):
            return self
        attributes = cast(
            Dict[str, IndividualType],
            {attr: sub(t) for attr, t in self._attributes.items()},
        )
        nominal_supertypes = [
            sub(supertype) for supertype in self._nominal_supertypes
        ]
        subbed_type = type(self)(
            self._self_type,
            attributes,
            nominal_supertypes=nominal_supertypes,
            nominal=self._nominal,
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
        rigid_variables: AbstractSet['_Variable'],
        subtyping_assumptions: List[Tuple[IndividualType, IndividualType]],
    ) -> 'Substitutions':
        from concat.typecheck import Substitutions

        if self is supertype or _contains_assumption(
            subtyping_assumptions, self, supertype
        ):
            return Substitutions()

        # obj <: `t, `t is not rigid
        # --> `t = obj
        if (
            isinstance(supertype, IndividualVariable)
            and supertype not in rigid_variables
        ):
            return Substitutions([(supertype, self)])
        # obj <: *s? `t...
        # error
        elif isinstance(supertype, (SequenceVariable, TypeSequence)):
            raise concat.typecheck.TypeError(
                '{} is an individual type, but {} is a sequence type'.format(
                    self, supertype
                )
            )

        if self.kind != supertype.kind:
            raise concat.typecheck.TypeError(
                f'{self} has kind {self.kind}, but {supertype} has kind {supertype.kind}'
            )

        if isinstance(supertype, (StackEffect, PythonFunctionType)):
            return self.get_type_of_attribute(
                '__call__'
            ).constrain_and_bind_variables(
                supertype,
                rigid_variables,
                subtyping_assumptions + [(self, supertype)],
            )
        if isinstance(supertype, _OptionalType):
            try:
                return self.constrain_and_bind_variables(
                    none_type,
                    rigid_variables,
                    subtyping_assumptions + [(self, supertype)],
                )
            except concat.typecheck.TypeError:
                return self.constrain_and_bind_variables(
                    supertype.type_arguments[0],
                    rigid_variables,
                    subtyping_assumptions + [(self, supertype)],
                )
        if not isinstance(supertype, ObjectType):
            raise NotImplementedError(supertype)
        # every object type is a subtype of object_type
        if supertype is get_object_type():
            return Substitutions()
        # Don't forget that there's nominal subtyping too.
        if supertype._nominal:
            if supertype in self._nominal_supertypes:
                return Substitutions()
            if self._head is not supertype._head:
                raise concat.typecheck.TypeError(
                    '{} is not a subtype of {}'.format(self, supertype)
                )

        # BUG
        subtyping_assumptions.append((self, supertype))

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
        return sub

    def get_type_of_attribute(self, attribute: str) -> Type:
        if attribute not in self._attributes:
            raise concat.typecheck.AttributeError(self, attribute)

        self_sub = concat.typecheck.Substitutions([(self._self_type, self)])

        return self_sub(self._attributes[attribute])

    def __repr__(self) -> str:
        head = None if self._head is self else self._head
        return f'{type(self).__qualname__}(self_type={self._self_type!r}, attributes={self._attributes!r}, nominal_supertypes={self._nominal_supertypes!r}, nominal={self._nominal!r}, _head={head!r})'

    def _free_type_variables(self) -> InsertionOrderedSet[_Variable]:
        ftv = free_type_variables_of_mapping(self.attributes)
        # QUESTION: Include supertypes?
        ftv -= {self.self_type}
        return ftv

    def __str__(self) -> str:
        if self._internal_name is not None:
            return self._internal_name
        return '{}({}, {}, {}, {}, {})'.format(
            type(self).__qualname__,
            self._self_type,
            _mapping_to_str(self._attributes),
            _iterable_to_str(self._nominal_supertypes),
            self._nominal,
            None if self._head is self else self._head,
        )

    _hash_variable = None

    def __hash__(self) -> int:
        from concat.typecheck import Substitutions

        if ObjectType._hash_variable is None:
            ObjectType._hash_variable = IndividualVariable()
        sub = Substitutions([(self._self_type, ObjectType._hash_variable)])
        type_to_hash = sub(self)
        return hash(
            (
                tuple(type_to_hash._attributes.items()),
                tuple(type_to_hash._nominal_supertypes),
                type_to_hash._nominal,
                None if type_to_hash._head == self else type_to_hash._head,
            )
        )

    @property
    def attributes(self) -> Mapping[str, Type]:
        from concat.typecheck import Substitutions

        sub = Substitutions([(self._self_type, self)])
        return {name: sub(ty) for name, ty in self._attributes.items()}

    @property
    def self_type(self) -> IndividualVariable:
        return self._self_type

    @property
    def head(self) -> 'ObjectType':
        return self._head

    @property
    def nominal_supertypes(self) -> Sequence[IndividualType]:
        return self._nominal_supertypes


# QUESTION: Should this exist, or should I use ObjectType
class ClassType(ObjectType):
    """The representation of types of classes, like in "Design and Evaluation of Gradual Typing for Python" (Vitousek et al. 2014)."""

    def constrain_and_bind_variables(
        self, supertype, rigid_variables, subtyping_assumptions
    ) -> 'Substitutions':
        if (
            not supertype.has_attribute('__call__')
            or '__init__' not in self._attributes
        ):
            return super().constrain_and_bind_variables(
                supertype, rigid_variables, subtyping_assumptions
            )
        init = self.get_type_of_attribute('__init__')
        while not isinstance(init, (StackEffect, PythonFunctionType)):
            init = init.get_type_of_attribute('__call__')
        bound_init = init.bind()
        return bound_init.constrain_and_bind_variables(
            supertype.get_type_of_attribute('__call__'),
            rigid_variables,
            subtyping_assumptions + [(self, supertype)],
        )


class PythonFunctionType(IndividualType):
    def __init__(
        self,
        _overloads: Sequence[
            Tuple[Sequence[StackItemType], IndividualType]
        ] = (),
        type_parameters: Sequence[_Variable] = (),
        _type_arguments: Sequence[Type] = (),
    ) -> None:
        super().__init__()
        self._arity = len(type_parameters)
        self._type_parameters = type_parameters
        self._type_arguments = _type_arguments
        if not (
            self._arity == 0
            and len(self._type_arguments) == 2
            or self._arity == 2
            and len(self._type_arguments) == 0
        ):
            raise concat.typecheck.TypeError(
                f'Ill-formed Python function type with arguments {self._type_arguments}'
            )
        if self._arity == 0:
            assert isinstance(self.input, collections.abc.Sequence)
            assert self._type_arguments[1].kind == IndividualKind()
        self._overloads = _overloads
        self._hash: Optional[int] = None

    def _free_type_variables(self) -> InsertionOrderedSet[_Variable]:
        if self._arity == 0:
            ftv = InsertionOrderedSet[_Variable]([])
            for ty in self.input:
                ftv |= ty.free_type_variables()
            ftv |= self.output.free_type_variables()
            return ftv
        else:
            return InsertionOrderedSet([])

    @property
    def kind(self) -> 'Kind':
        if self._arity == 0:
            return IndividualKind()
        return GenericTypeKind([SequenceKind(), IndividualKind()])

    def resolve_forward_references(self) -> 'PythonFunctionType':
        if self._forward_references_resolved:
            return self
        super().resolve_forward_references()
        overloads: List[Tuple[Sequence[StackItemType], IndividualType]] = []
        for args, ret in overloads:
            overloads.append(
                (
                    [arg.resolve_forward_references() for arg in args],
                    ret.resolve_forward_references(),
                )
            )
        self._overloads = overloads
        self._type_arguments = list(
            t.resolve_forward_references() for t in self._type_arguments
        )
        return self

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, PythonFunctionType):
            return False
        if self.kind != other.kind:
            return False
        if isinstance(self.kind, GenericTypeKind):
            return True
        return (
            tuple(self.input) == tuple(other.input)
            and self.output == other.output
        )

    def __hash__(self) -> int:
        if self._hash is None:
            self._hash = self._compute_hash()
        return self._hash

    def _compute_hash(self) -> int:
        if isinstance(self.kind, GenericTypeKind):
            return 1
        return hash((tuple(self.input), self.output))

    def __repr__(self) -> str:
        # QUESTION: Is it worth using type(self)?
        return f'{type(self).__qualname__}(_overloads={self._overloads!r}, type_parameters={self._type_parameters!r}, _type_arguments={self._type_arguments})'

    def __str__(self) -> str:
        if not self._type_arguments:
            return 'py_function_type'
        return 'py_function_type[{}, {}]'.format(
            _iterable_to_str(self.input), self.output
        )

    def get_type_of_attribute(self, attribute: str) -> Type:
        if attribute == '__call__':
            return self
        else:
            return super().get_type_of_attribute(attribute)

    @property
    def attributes(self) -> Mapping[str, Type]:
        return {**super().attributes, '__call__': self}

    def __getitem__(
        self, arguments: Tuple[TypeSequence, IndividualType]
    ) -> 'PythonFunctionType':
        if self._arity != 2:
            raise concat.typecheck.TypeError(f'{self} is not a generic type')
        if len(arguments) != 2:
            raise concat.typecheck.TypeError(
                f'{self} takes two arguments, got {len(arguments)}'
            )
        input = arguments[0]
        output = arguments[1]
        if input.kind != SequenceKind():
            raise concat.typecheck.TypeError(
                f'First argument to {self} must be a sequence type of function arguments'
            )
        if output.kind != IndividualKind():
            raise concat.typecheck.TypeError(
                f'Second argument to {self} must be an individual type for the return type'
            )
        return PythonFunctionType(
            _type_arguments=(input, output), type_parameters=(), _overloads=[],
        )

    def apply_substitution(
        self, sub: 'concat.typecheck.Substitutions'
    ) -> 'PythonFunctionType':
        if self._arity == 0:
            inp = sub(TypeSequence(self.input))
            out = sub(self.output)
            overloads: Sequence[Tuple[TypeSequence, IndividualType]] = [
                (sub(TypeSequence(i)), sub(o)) for i, o in self._overloads
            ]
            return PythonFunctionType(
                _type_arguments=(inp, out), _overloads=overloads
            )
        return self

    @property
    def input(self) -> Sequence[StackItemType]:
        assert self._arity == 0
        if isinstance(self._type_arguments[0], SequenceVariable):
            return (self._type_arguments[0],)
        assert not isinstance(self._type_arguments[0], IndividualType)
        return tuple(self._type_arguments[0])

    @property
    def output(self) -> IndividualType:
        assert self._arity == 0
        assert self._type_arguments[1].kind == IndividualKind()
        return self._type_arguments[1]

    def select_overload(
        self, input_types: Sequence[StackItemType]
    ) -> Tuple['PythonFunctionType', 'Substitutions']:
        for overload in [(self.input, self.output), *self._overloads]:
            try:
                sub = TypeSequence(input_types).constrain_and_bind_variables(
                    TypeSequence(overload[0]), set(), []
                )
            except TypeError:
                continue
            return (
                sub(py_function_type[TypeSequence(overload[0]), overload[1]]),
                sub,
            )
        raise concat.typecheck.TypeError(
            'no overload of {} matches types {}'.format(self, input_types)
        )

    def with_overload(
        self, input: Sequence[StackItemType], output: IndividualType
    ) -> 'PythonFunctionType':
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
        rigid_variables: AbstractSet['_Variable'],
        subtyping_assumptions: List[Tuple[IndividualType, IndividualType]],
    ) -> 'Substitutions':
        from concat.typecheck import Substitutions

        if self is supertype or _contains_assumption(
            subtyping_assumptions, self, supertype
        ):
            return Substitutions()
        if self.kind != supertype.kind:
            raise concat.typecheck.TypeError(
                f'{self} has kind {self.kind} but {supertype} has kind {supertype.kind}'
            )
        if self.kind == IndividualKind():
            if (
                isinstance(supertype, IndividualVariable)
                and supertype not in rigid_variables
            ):
                return Substitutions([(supertype, self)])
            if isinstance(supertype, _OptionalType):
                return self.constrain_and_bind_variables(
                    supertype.type_arguments[0],
                    rigid_variables,
                    subtyping_assumptions,
                )
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
                return sub
        if isinstance(supertype, PythonFunctionType):
            if isinstance(self.kind, GenericTypeKind):
                return Substitutions()

            # No need to extend the rigid variables, we know both types have no
            # parameters at this point.

            # Support overloading the subtype.
            for overload in [
                (self.input, self.output),
                *self._overloads,
            ]:
                try:
                    subtyping_assumptions_copy = subtyping_assumptions[:]
                    self_input_types = TypeSequence(overload[0])
                    supertype_input_types = TypeSequence(supertype.input)
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
                    return sub
                except concat.typecheck.TypeError:
                    continue
                finally:
                    subtyping_assumptions[:] = subtyping_assumptions_copy

        raise concat.typecheck.TypeError(
            'no overload of {} is a subtype of {}'.format(self, supertype)
        )


class _PythonOverloadedType(Type):
    def __init__(self) -> None:
        super().__init__()

    def __getitem__(self, args: Sequence[Type]) -> 'PythonFunctionType':
        import concat.typecheck

        if len(args) == 0:
            raise concat.typecheck.TypeError(
                'py_overloaded must be applied to at least one argument'
            )
        for arg in args:
            if not isinstance(arg, PythonFunctionType):
                raise concat.typecheck.TypeError(
                    'Arguments to py_overloaded must be Python function types'
                )
        fun_type = args[0]
        for arg in args[1:]:
            fun_type = fun_type.with_overload(arg.input, arg.output)
        return fun_type

    @property
    def attributes(self) -> Mapping[str, 'Type']:
        raise concat.typecheck.TypeError(
            'py_overloaded does not have attributes'
        )

    def _free_type_variables(self) -> InsertionOrderedSet['_Variable']:
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
        rigid_variables: AbstractSet['_Variable'],
        subtyping_assumptions: List[Tuple['IndividualType', 'IndividualType']],
    ) -> 'Substitutions':
        raise concat.typecheck.TypeError('py_overloaded is a generic type')

    def resolve_forward_references(self) -> '_PythonOverloadedType':
        return self

    @property
    def kind(self) -> 'Kind':
        return GenericTypeKind([SequenceKind()])

    def __hash__(self) -> int:
        return hash(type(self).__qualname__)

    def __eq__(self, other: object) -> bool:
        return isinstance(other, type(self))


py_overloaded_type = _PythonOverloadedType()


class _NoReturnType(ObjectType):
    def __init__(self) -> None:
        x = IndividualVariable()
        super().__init__(x, {})

    def is_subtype_of(self, _: Type) -> Literal[True]:
        return True

    def apply_substitution(
        self, sub: 'concat.typecheck.Substitutions'
    ) -> '_NoReturnType':
        return self

    def __repr__(self) -> str:
        return '{}()'.format(type(self).__qualname__)


class _OptionalType(IndividualType):
    def __init__(self, type_argument: IndividualType) -> None:
        super().__init__()
        while isinstance(type_argument, _OptionalType):
            type_argument = type_argument._type_argument
        self._type_argument: IndividualType = type_argument

    def __repr__(self) -> str:
        return f'{type(self).__qualname__}({self._type_argument!r})'

    def __str__(self) -> str:
        return f'optional_type[{self._type_argument}]'

    def _free_type_variables(self) -> InsertionOrderedSet[_Variable]:
        return self._type_argument.free_type_variables()

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, _OptionalType):
            return False
        return self._type_argument == other._type_argument

    def __hash__(self) -> int:
        return hash(self._type_argument)

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
            raise concat.typecheck.TypeError(
                f'{self} is an individual type, but {supertype} has kind {supertype.kind}'
            )
        # FIXME: optional[none] should simplify to none
        if self._type_argument is none_type and supertype is none_type:
            return Substitutions()

        sub = none_type.constrain_and_bind_variables(
            supertype, rigid_variables, subtyping_assumptions
        )
        sub = sub(self._type_argument).constrain_and_bind_variables(
            sub(supertype), rigid_variables, subtyping_assumptions
        )
        return sub

    def resolve_forward_references(self) -> '_OptionalType':
        self._type_argument = self._type_argument.resolve_forward_references()
        return self

    def apply_substitution(
        self, sub: 'concat.typecheck.Substitutions'
    ) -> '_OptionalType':
        return _OptionalType(sub(self._type_argument))

    @property
    def type_arguments(self) -> Sequence[IndividualType]:
        return [self._type_argument]


class Kind(abc.ABC):
    @abc.abstractmethod
    def __eq__(self, other: object) -> bool:
        pass

    @abc.abstractmethod
    def __hash__(self) -> int:
        pass


class IndividualKind(Kind):
    def __eq__(self, other: object) -> bool:
        return isinstance(other, IndividualKind)

    def __hash__(self) -> int:
        return hash(type(self).__qualname__)


class SequenceKind(Kind):
    def __eq__(self, other: object) -> bool:
        return isinstance(other, SequenceKind)

    def __hash__(self) -> int:
        return hash(type(self).__qualname__)


class GenericTypeKind(Kind):
    def __init__(self, parameter_kinds: Sequence[Kind]) -> None:
        assert parameter_kinds
        self.parameter_kinds = parameter_kinds

    def __eq__(self, other: object) -> bool:
        return (
            isinstance(other, GenericTypeKind)
            and self.parameter_kinds == other.parameter_kinds
        )

    def __hash__(self) -> int:
        return hash(tuple(self.parameter_kinds))


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

    def __hash__(self) -> int:
        if self._resolved_type is not None:
            return hash(self._resolved_type)
        return hash(self._as_hashable_tuple())

    def __eq__(self, other: object) -> bool:
        if super().__eq__(other):
            return True
        if not isinstance(other, Type):
            return NotImplemented
        if self._resolved_type is not None:
            return self._resolved_type == other
        if not isinstance(other, ForwardTypeReference):
            return False
        return self._as_hashable_tuple() == other._as_hashable_tuple()

    def __getitem__(self, args: TypeArguments) -> IndividualType:
        if self._resolved_type is not None:
            return self._resolved_type[args]

        if isinstance(self.kind, GenericTypeKind):
            if len(self.kind.parameter_kinds) != len(args):
                raise concat.typecheck.TypeError(
                    'Wrong number of arguments to generic type'
                )
            for kind, arg in zip(self.kind.parameter_kinds, args):
                if kind != arg.kind:
                    raise concat.typecheck.TypeError(
                        f'Type argument has kind {arg.kind}, expected kind {kind}'
                    )
            return ForwardTypeReference(
                IndividualKind(),
                self._name_to_resolve,
                self._resolution_env,
                _type_arguments=args,
            )
        raise concat.typecheck.TypeError(f'{self} is not a generic type')

    def resolve_forward_references(self) -> Type:
        if self._resolved_type is None:
            self._resolved_type = self._resolve()
        return self._resolved_type

    def apply_substitution(
        self, sub: 'concat.typecheck.Substitutions'
    ) -> 'ForwardTypeReference':
        if self._resolved_type is not None:
            return sub(self._resolved_type)

        return self

    @property
    def attributes(self) -> Mapping[str, Type]:
        if self._resolved_type is not None:
            return self._resolved_type.attributes

        raise concat.typecheck.TypeError(
            'Cannot access attributes of type before they are defined'
        )

    def constrain_and_bind_variables(
        self,
        supertype: Type,
        rigid_variables: AbstractSet['_Variable'],
        subtyping_assumptions: List[Tuple[IndividualType, IndividualType]],
    ) -> 'Substitutions':
        if self is supertype:
            return concat.typecheck.Substitutions()

        if self._resolved_type is not None:
            return self._resolved_type.constrain_and_bind_variables(
                supertype, rigid_variables, subtyping_assumptions
            )

        raise concat.typecheck.TypeError(
            'Supertypes of type are not known before its definition'
        )

    def _free_type_variables(self) -> InsertionOrderedSet[_Variable]:
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

_x = IndividualVariable()

float_type = ObjectType(_x, {}, nominal=True)
no_return_type = _NoReturnType()


_object_type: Optional[Type] = None


def get_object_type() -> Type:
    assert _object_type is not None
    return _object_type


def set_object_type(ty: Type) -> None:
    global _object_type
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


_arg_type_var = SequenceVariable()
_return_type_var = IndividualVariable()
py_function_type = PythonFunctionType(
    type_parameters=[_arg_type_var, _return_type_var]
)
py_function_type.set_internal_name('py_function_type')

_invert_result_var = IndividualVariable()
invertible_type = GenericType(
    [_invert_result_var],
    ObjectType(
        _x,
        {'__invert__': py_function_type[TypeSequence([]), _invert_result_var]},
    ),
)

_sub_operand_type = IndividualVariable()
_sub_result_type = IndividualVariable()
# FIXME: Add reverse_substractable_type for __rsub__
subtractable_type = GenericType(
    [_sub_operand_type, _sub_result_type],
    ObjectType(
        _x,
        {
            '__sub__': py_function_type[
                TypeSequence([_sub_operand_type]), _sub_result_type
            ]
        },
    ),
)
subtractable_type.set_internal_name('subtractable_type')

_add_other_operand_type = IndividualVariable()
_add_result_type = IndividualVariable()

addable_type = GenericType(
    [_add_other_operand_type, _add_result_type],
    ObjectType(
        _x,
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

bool_type = ObjectType(_x, {}, nominal=True)
bool_type.set_internal_name('bool_type')

# QUESTION: Allow comparison methods to return any object?

_other_type = IndividualVariable()
geq_comparable_type = GenericType(
    [_other_type],
    ObjectType(
        _x,
        {'__ge__': py_function_type[TypeSequence([_other_type]), bool_type]},
    ),
)
geq_comparable_type.set_internal_name('geq_comparable_type')

leq_comparable_type = GenericType(
    [_other_type],
    ObjectType(
        _x,
        {'__le__': py_function_type[TypeSequence([_other_type]), bool_type]},
    ),
)
leq_comparable_type.set_internal_name('leq_comparable_type')

lt_comparable_type = GenericType(
    [_other_type],
    ObjectType(
        _x,
        {'__lt__': py_function_type[TypeSequence([_other_type]), bool_type]},
    ),
)
lt_comparable_type.set_internal_name('lt_comparable_type')

_int_add_type = py_function_type[TypeSequence([_x]), _x]

int_type = ObjectType(
    _x,
    {
        '__add__': _int_add_type,
        '__invert__': py_function_type[TypeSequence([]), _x],
        '__sub__': _int_add_type,
        '__le__': py_function_type[TypeSequence([_x]), bool_type],
        '__lt__': py_function_type[TypeSequence([_x]), bool_type],
        '__ge__': py_function_type[TypeSequence([_x]), bool_type],
    },
    nominal=True,
)
int_type.set_internal_name('int_type')

none_type = ObjectType(_x, {})
none_type.set_internal_name('none_type')

_result_type = IndividualVariable()

iterator_type = GenericType(
    [_result_type],
    ObjectType(
        _x,
        {
            '__iter__': py_function_type[TypeSequence([]), _x],
            '__next__': py_function_type[
                TypeSequence([none_type,]), _result_type
            ],
        },
    ),
)
iterator_type.set_internal_name('iterator_type')

iterable_type = GenericType(
    [_result_type],
    ObjectType(
        _x,
        {
            '__iter__': py_function_type[
                TypeSequence([]), iterator_type[_result_type,]
            ]
        },
    ),
)
iterable_type.set_internal_name('iterable_type')

context_manager_type = ObjectType(
    _x,
    {
        # TODO: Add argument and return types. I think I'll need a special
        # py_function representation for that.
        '__enter__': py_function_type,
        '__exit__': py_function_type,
    },
)
context_manager_type.set_internal_name('context_manager_type')

_optional_type_var = IndividualVariable()
optional_type = GenericType(
    [_optional_type_var], _OptionalType(_optional_type_var)
)
optional_type.set_internal_name('optional_type')

_key_type_var = IndividualVariable()
_value_type_var = IndividualVariable()
dict_type = ObjectType(
    _x,
    {
        '__iter__': py_function_type[
            TypeSequence([]), iterator_type[_key_type_var,]
        ]
    },
    [_key_type_var, _value_type_var],
    nominal=True,
)
dict_type.set_internal_name('dict_type')

file_type = ObjectType(
    self_type=_x,
    attributes={
        'seek': py_function_type[TypeSequence([int_type]), int_type],
        'read': py_function_type,
        '__enter__': py_function_type,
        '__exit__': py_function_type,
    },
    # context_manager_type is a structural supertype
    nominal=True,
)
file_type.set_internal_name('file_type')

_start_type_var, _stop_type_var, _step_type_var = (
    IndividualVariable(),
    IndividualVariable(),
    IndividualVariable(),
)
slice_type = ObjectType(
    _x, {}, [_start_type_var, _stop_type_var, _step_type_var], nominal=True
)
slice_type.set_internal_name('slice_type')

ellipsis_type = ObjectType(_x, {})
not_implemented_type = ObjectType(_x, {})

_element_types_var = SequenceVariable()
tuple_type = GenericType(
    [_element_types_var],
    ObjectType(
        _x,
        {'__getitem__': py_function_type},
        nominal=True,
        # iterable_type is a structural supertype
    ),
    is_variadic=True,
)
tuple_type.set_internal_name('tuple_type')

base_exception_type = ObjectType(_x, {})
module_type = ObjectType(_x, {})

_index_type_var = IndividualVariable()
_result_type_var = IndividualVariable()
subscriptable_type = ObjectType(
    IndividualVariable(),
    {
        '__getitem__': py_function_type[
            TypeSequence([_index_type_var]), _result_type_var
        ],
    },
    [_index_type_var, _result_type_var],
)

_answer_type_var = IndividualVariable()
continuation_monad_type = ObjectType(
    _x, {}, [_result_type_var, _answer_type_var], nominal=True
)
continuation_monad_type.set_internal_name('continuation_monad_type')
