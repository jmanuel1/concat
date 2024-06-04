from concat.orderedset import InsertionOrderedSet
import concat.typecheck
from concat.typecheck.errors import (
    AttributeError as ConcatAttributeError,
    StackMismatchError,
    StaticAnalysisError,
    TypeError as ConcatTypeError,
)
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
from typing_extensions import Self
import abc


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
            InsertionOrderedSet[_Variable]
        ] = None
        self._internal_name: Optional[str] = None
        self._forward_references_resolved = False
        self._type_id = Type._next_type_id
        Type._next_type_id += 1

    # QUESTION: Do I need this?
    def is_subtype_of(self, supertype: 'Type') -> SubtypeExplanation:
        try:
            sub = self.constrain_and_bind_variables(supertype, set(), [])
        except ConcatTypeError as e:
            return SubtypeExplanation(e)
        return SubtypeExplanation(sub)

    # No <= implementation using subtyping, because variables overload that for
    # sort by identity.

    def __eq__(self, other: object) -> bool:
        if self is other:
            return True
        if not isinstance(other, Type):
            return NotImplemented
        # QUESTION: Define == separately from is_subtype_of?
        return self.is_subtype_of(other) and other.is_subtype_of(self)

    # NOTE: Avoid hashing types. I might I'm having correctness issues related
    # to hashing that I'd rather avoid entirely. Maybe one day I'll introduce
    # hash consing, but that would only reflect syntactic eequality, and I've
    # been using hashing for type equality.

    # TODO: Define in terms of .attributes
    def get_type_of_attribute(self, name: str) -> 'Type':
        raise ConcatAttributeError(self, name)

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

    @abc.abstractmethod
    def resolve_forward_references(self) -> 'Type':
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

    def __getitem__(self, _: Any) -> Any:
        raise ConcatTypeError(
            f'{self} is neither a generic type nor a sequence type'
        )


class IndividualType(Type):
    def instantiate(self) -> 'IndividualType':
        return cast(IndividualType, super().instantiate())

    @property
    def kind(self) -> 'Kind':
        return IndividualKind()

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

    def _free_type_variables(self) -> InsertionOrderedSet['_Variable']:
        ftv = self._head.free_type_variables()
        for arg in self._args:
            ftv |= arg.free_type_variables()
        return ftv

    def resolve_forward_references(self) -> Type:
        head = self._head.resolve_forward_references()
        args = [arg.resolve_forward_references() for arg in self._args]
        return head[args]


class _Variable(Type, abc.ABC):
    """Objects that represent type variables.

    Every type variable object is assumed to be unique. Thus, fresh type
    variables can be made simply by creating new objects. They can also be
    compared by identity."""

    def apply_substitution(
        self, sub: 'concat.typecheck.Substitutions'
    ) -> Union['IndividualType', '_Variable', 'TypeSequence']:
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
        return self is other

    def resolve_forward_references(self) -> '_Variable':
        return self

    # NOTE: This hash impl is kept because sets of variables are fine and
    # variables are simple.
    def __hash__(self) -> int:
        """Hash a variable by its identity.

        __hash__ by object identity is used since that's the only way for two
        type variables to be ==."""

        return hash(id(self))


class BoundVariable(_Variable):
    def __init__(self, kind: 'Kind') -> None:
        super().__init__()
        self._kind = kind

    @property
    def kind(self) -> 'Kind':
        return self._kind

    def constrain_and_bind_variables(
        self, supertype, rigid_variables, subtyping_assumptions
    ) -> 'Substitutions':
        raise TypeError('Cannot constrain bound variables')

    def __getitem__(self, args: 'TypeArguments') -> Type:
        assert isinstance(self.kind, GenericTypeKind)
        assert list(self.kind.parameter_kinds) == [t.kind for t in args]
        return StuckTypeApplication(self, args)

    def __repr__(self) -> str:
        return f'<bound variable {id(self)}>'

    def __str__(self) -> str:
        return f't_{id(self)}'

    @property
    def attributes(self) -> Mapping[str, Type]:
        raise TypeError('Cannot get attributes of bound variables')


class IndividualVariable(_Variable, IndividualType):
    def constrain_and_bind_variables(
        self,
        supertype: Type,
        rigid_variables: AbstractSet['_Variable'],
        subtyping_assumptions: List[Tuple['Type', 'Type']],
    ) -> 'Substitutions':
        from concat.typecheck import Substitutions

        if self is supertype or supertype is get_object_type():
            return Substitutions()
        if supertype.kind != IndividualKind():
            raise ConcatTypeError(
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
            except ConcatTypeError:
                return self.constrain_and_bind_variables(
                    none_type, rigid_variables, subtyping_assumptions
                )
        if self in rigid_variables:
            raise ConcatTypeError(
                f'{self} is considered fixed here and cannot become a subtype of {supertype}'
            )
        mapping = {self: supertype}
        return Substitutions(mapping)

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
        raise ConcatTypeError(
            '{} is an individual type variable, so its attributes are unknown'.format(
                self
            )
        )

    @property
    def kind(self) -> 'Kind':
        return IndividualKind()


class SequenceVariable(_Variable):
    def __init__(self) -> None:
        super().__init__()

    def __str__(self) -> str:
        return '*t_{}'.format(id(self))

    def __repr__(self) -> str:
        return f'<sequence variable {id(self)}>'

    def constrain_and_bind_variables(
        self,
        supertype: Type,
        rigid_variables: AbstractSet['_Variable'],
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

    def get_type_of_attribute(self, name: str) -> NoReturn:
        raise ConcatTypeError(
            'the sequence type {} does not hold attributes'.format(self)
        )

    @property
    def attributes(self) -> NoReturn:
        raise ConcatTypeError(
            'the sequence type {} does not hold attributes'.format(self)
        )

    @property
    def kind(self) -> 'Kind':
        return SequenceKind()


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
            raise ConcatTypeError(
                f'Cannot be polymorphic over non-individual type {body}'
            )
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
        actual_kinds = [ty.kind for ty in type_arguments]
        if expected_kinds != actual_kinds:
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
    def kind(self) -> 'Kind':
        kinds = [var.kind for var in self._type_parameters]
        return GenericTypeKind(kinds)

    def resolve_forward_references(self) -> 'GenericType':
        body = self._body.resolve_forward_references()
        return GenericType(self._type_parameters, body, self.is_variadic)

    def instantiate(self) -> Type:
        fresh_vars: Sequence[_Variable] = [
            type(var)() for var in self._type_parameters
        ]
        return self[fresh_vars]

    def constrain_and_bind_variables(
        self,
        supertype: 'Type',
        rigid_variables: AbstractSet['_Variable'],
        subtyping_assumptions: List[Tuple['Type', 'Type']],
    ) -> 'Substitutions':
        from concat.typecheck import Substitutions

        if self is supertype or _contains_assumption(
            subtyping_assumptions, self, supertype
        ):
            return Substitutions([])
        if self.kind != supertype.kind:
            raise ConcatTypeError(
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
        raise ConcatTypeError(
            'Generic types do not have attributes; maybe you forgot type arguments?'
        )

    def _free_type_variables(self) -> InsertionOrderedSet['_Variable']:
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
        rigid_variables: AbstractSet['_Variable'],
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
            elif not self._individual_types:
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
                else:
                    raise StackMismatchError(self, supertype)
            else:
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
                        # sub.add_subtyping_provenance((self, supertype))
                        return sub
                    except StackMismatchError:
                        # TODO: Add info about occurs check and rigid
                        # variables.
                        raise StackMismatchError(self, supertype)
                else:
                    raise StackMismatchError(self, supertype)
        else:
            raise ConcatTypeError(
                f'{self} is a sequence type, not {supertype}'
            )

    def _free_type_variables(self) -> InsertionOrderedSet['_Variable']:
        ftv: InsertionOrderedSet[_Variable] = InsertionOrderedSet([])
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

    def resolve_forward_references(self) -> 'TypeSequence':
        individual_types = [
            t.resolve_forward_references() for t in self._individual_types
        ]
        rest = [] if self._rest is None else [self._rest]
        return TypeSequence(rest + individual_types)

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
                raise ConcatTypeError(f'{ty} must be an individual type')
        for ty in output_types[1:]:
            if ty.kind != IndividualKind():
                raise ConcatTypeError(f'{ty} must be an individual type')
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
        rigid_variables: AbstractSet['_Variable'],
        subtyping_assumptions: List[Tuple['Type', 'Type']],
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
        raise ConcatAttributeError(self, name)

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
        input = self.input.resolve_forward_references()
        output = self.output.resolve_forward_references()
        return StackEffect(input, output)


class QuotationType(_Function):
    def __init__(self, fun_type: _Function) -> None:
        super().__init__(fun_type.input, fun_type.output)

    def constrain_and_bind_variables(
        self,
        supertype: Type,
        rigid_variables: AbstractSet['_Variable'],
        subtyping_assumptions: List[Tuple['Type', 'Type']],
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
        attributes: Mapping[str, Type],
        nominal_supertypes: Sequence[Type] = (),
        nominal: bool = False,
        _head: Optional['ObjectType'] = None,
    ) -> None:
        super().__init__()

        self._attributes = attributes

        for t in nominal_supertypes:
            if t.kind != IndividualKind():
                raise ConcatTypeError(
                    f'{t} must be an individual type, but has kind {t.kind}'
                )
        self._nominal_supertypes = nominal_supertypes

        self._nominal = nominal

        self._head = _head or self

        self._internal_name: Optional[str] = None
        self._internal_name = self._head._internal_name

    @property
    def nominal(self) -> bool:
        return self._nominal

    def resolve_forward_references(self) -> 'ObjectType':
        attributes = {
            attr: t.resolve_forward_references()
            for attr, t in self._attributes.items()
        }
        nominal_supertypes = [
            t.resolve_forward_references() for t in self._nominal_supertypes
        ]
        return ObjectType(
            attributes, nominal_supertypes, self.nominal, self._head
        )

    @property
    def kind(self) -> 'Kind':
        return IndividualKind()

    def apply_substitution(
        self, sub: 'concat.typecheck.Substitutions',
    ) -> 'ObjectType':
        from concat.typecheck import Substitutions

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
        subtyping_assumptions: List[Tuple['Type', 'Type']],
    ) -> 'Substitutions':
        from concat.typecheck import Substitutions

        if self is supertype or _contains_assumption(
            subtyping_assumptions, self, supertype
        ):
            sub = Substitutions()
            sub.add_subtyping_provenance((self, supertype))
            return sub

        # obj <: `t, `t is not rigid
        # --> `t = obj
        if (
            isinstance(supertype, IndividualVariable)
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

        if self.kind != supertype.kind:
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
                    none_type,
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
        if not isinstance(supertype, ObjectType):
            raise NotImplementedError(supertype)
        # every object type is a subtype of object_type
        if supertype is get_object_type():
            sub = Substitutions()
            sub.add_subtyping_provenance((self, supertype))
            return sub
        # Don't forget that there's nominal subtyping too.
        if supertype._nominal:
            if supertype in self._nominal_supertypes:
                sub = Substitutions()
                sub.add_subtyping_provenance((self, supertype))
                return sub
            if self._head is not supertype._head:
                raise ConcatTypeError(
                    '{} is not a subtype of {}'.format(self, supertype)
                )

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

    def get_type_of_attribute(self, attribute: str) -> Type:
        if attribute not in self._attributes:
            raise ConcatAttributeError(self, attribute)

        return self._attributes[attribute]

    def __repr__(self) -> str:
        head = None if self._head is self else self._head
        return f'{type(self).__qualname__}(attributes={self._attributes!r}, nominal_supertypes={self._nominal_supertypes!r}, nominal={self._nominal!r}, _head={head!r})'

    def _free_type_variables(self) -> InsertionOrderedSet[_Variable]:
        ftv = free_type_variables_of_mapping(self.attributes)
        # QUESTION: Include supertypes?
        return ftv

    def __str__(self) -> str:
        if self._internal_name is not None:
            return self._internal_name
        return f'ObjectType({_mapping_to_str(self._attributes)}, {_iterable_to_str(self._nominal_supertypes)}, {self._nominal}, {None if self._head is self else self._head})'

    @property
    def attributes(self) -> Mapping[str, Type]:
        return self._attributes

    @property
    def head(self) -> 'ObjectType':
        return self._head

    @property
    def nominal_supertypes(self) -> Sequence[Type]:
        return self._nominal_supertypes


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
        type_parameters: Sequence[_Variable] = (),
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
            if i.kind != SequenceKind():
                raise ConcatTypeError(
                    f'{i} must be a sequence type, but has kind {i.kind}'
                )
            # HACK: Sequence variables are introduced by the type sequence AST nodes
            if (
                isinstance(i, TypeSequence)
                and i
                and i[0].kind == SequenceKind()
            ):
                i = TypeSequence(i.as_sequence()[1:])
            _type_arguments = i, o
            if o.kind != IndividualKind():
                raise ConcatTypeError(
                    f'{o} must be an individual type, but has kind {o.kind}'
                )
            _fixed_overloads: List[Tuple[Type, Type]] = []
            for i, o in _overloads:
                if i.kind != SequenceKind():
                    raise ConcatTypeError(
                        f'{i} must be a sequence type, but has kind {i.kind}'
                    )
                if (
                    isinstance(i, TypeSequence)
                    and i
                    and i[0].kind == SequenceKind()
                ):
                    i = TypeSequence(i.as_sequence()[1:])
                if o.kind != IndividualKind():
                    raise ConcatTypeError(
                        f'{o} must be an individual type, but has kind {o.kind}'
                    )
                _fixed_overloads.append((i, o))
            self._overloads = _fixed_overloads
            self._type_arguments = _type_arguments

    def _free_type_variables(self) -> InsertionOrderedSet[_Variable]:
        if self._arity == 0:
            ftv = self.input.free_type_variables()
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
        if self._arity == 2:
            return self
        overloads: List[Tuple[Type, Type]] = []
        for args, ret in overloads:
            overloads.append(
                (
                    args.resolve_forward_references(),
                    ret.resolve_forward_references(),
                )
            )
        type_arguments = list(
            t.resolve_forward_references() for t in self._type_arguments
        )
        return PythonFunctionType(
            _overloads=overloads,
            type_parameters=[],
            _type_arguments=type_arguments,
        )

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, PythonFunctionType):
            return False
        if self.kind != other.kind:
            return False
        if isinstance(self.kind, GenericTypeKind):
            return True
        return self.input == other.input and self.output == other.output

    def __repr__(self) -> str:
        # QUESTION: Is it worth using type(self)?
        return f'{type(self).__qualname__}(_overloads={self._overloads!r}, type_parameters={self._type_parameters!r}, _type_arguments={self._type_arguments})'

    def __str__(self) -> str:
        if not self._type_arguments:
            return 'py_function_type'
        return f'py_function_type[{self.input}, {self.output}]'

    def get_type_of_attribute(self, attribute: str) -> Type:
        if attribute == '__call__':
            return self
        else:
            return super().get_type_of_attribute(attribute)

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
        if input.kind != SequenceKind():
            raise ConcatTypeError(
                f'First argument to {self} must be a sequence type of function arguments'
            )
        if output.kind != IndividualKind():
            raise ConcatTypeError(
                f'Second argument to {self} must be an individual type for the return type'
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
        rigid_variables: AbstractSet['_Variable'],
        subtyping_assumptions: List[Tuple['Type', 'Type']],
    ) -> 'Substitutions':
        from concat.typecheck import Substitutions

        if self is supertype or _contains_assumption(
            subtyping_assumptions, self, supertype
        ):
            sub = Substitutions()
            sub.add_subtyping_provenance((self, supertype))
            return sub
        if self.kind != supertype.kind:
            raise ConcatTypeError(
                f'{self} has kind {self.kind} but {supertype} has kind {supertype.kind}'
            )
        if self.kind == IndividualKind():
            if supertype is get_object_type():
                sub = Substitutions()
                sub.add_subtyping_provenance((self, supertype))
                return sub
            if (
                isinstance(supertype, IndividualVariable)
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
            if isinstance(self.kind, GenericTypeKind):
                sub = Substitutions()
                sub.add_subtyping_provenance((self, supertype))
                return sub

            # No need to extend the rigid variables, we know both types have no
            # parameters at this point.

            # Support overloading the subtype.
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
                except ConcatTypeError:
                    continue
                finally:
                    subtyping_assumptions[:] = subtyping_assumptions_copy

        raise ConcatTypeError(
            'no overload of {} is a subtype of {}'.format(self, supertype)
        )


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
        subtyping_assumptions: List[Tuple['Type', 'Type']],
    ) -> 'Substitutions':
        raise ConcatTypeError('py_overloaded is a generic type')

    def resolve_forward_references(self) -> '_PythonOverloadedType':
        return self

    @property
    def kind(self) -> 'Kind':
        return GenericTypeKind([SequenceKind()])

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

    def _free_type_variables(self) -> InsertionOrderedSet['_Variable']:
        return InsertionOrderedSet([])

    def resolve_forward_references(self) -> Self:
        return self


class _OptionalType(IndividualType):
    def __init__(self, type_argument: Type) -> None:
        super().__init__()
        if type_argument.kind != IndividualKind():
            raise ConcatTypeError(
                f'{type_argument} must be an individual type, but has kind {type_argument.kind}'
            )
        while isinstance(type_argument, _OptionalType):
            type_argument = type_argument._type_argument
        self._type_argument: Type = type_argument

    def __repr__(self) -> str:
        return f'{type(self).__qualname__}({self._type_argument!r})'

    def __str__(self) -> str:
        return f'optional_type[{self._type_argument}]'

    def _free_type_variables(self) -> InsertionOrderedSet[_Variable]:
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
        type_argument = self._type_argument.resolve_forward_references()
        return _OptionalType(type_argument)

    def apply_substitution(
        self, sub: 'concat.typecheck.Substitutions'
    ) -> '_OptionalType':
        return _OptionalType(sub(self._type_argument))

    @property
    def type_arguments(self) -> Sequence[Type]:
        return [self._type_argument]


class Kind(abc.ABC):
    @abc.abstractmethod
    def __eq__(self, other: object) -> bool:
        pass


class IndividualKind(Kind):
    def __eq__(self, other: object) -> bool:
        return isinstance(other, IndividualKind)


class SequenceKind(Kind):
    def __eq__(self, other: object) -> bool:
        return isinstance(other, SequenceKind)


class GenericTypeKind(Kind):
    def __init__(self, parameter_kinds: Sequence[Kind]) -> None:
        assert parameter_kinds
        self.parameter_kinds = parameter_kinds

    def __eq__(self, other: object) -> bool:
        return (
            isinstance(other, GenericTypeKind)
            and self.parameter_kinds == other.parameter_kinds
        )


class Fix(Type):
    def __init__(self, var: _Variable, body: Type) -> None:
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
        return self._unrolled_ty

    def _free_type_variables(self) -> InsertionOrderedSet[_Variable]:
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

    def get_type_of_attribute(self, name: str) -> Type:
        return self.attributes[name]

    def constrain_and_bind_variables(
        self, supertype, rigid_variables, subtyping_assumptions
    ) -> 'Substitutions':
        from concat.typecheck import Substitutions

        if supertype is get_object_type() or _contains_assumption(
            subtyping_assumptions, self, supertype
        ):
            sub = Substitutions()
            sub.add_subtyping_provenance((self, supertype))
            return sub

        if isinstance(supertype, Fix):
            unrolled = supertype.unroll()
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

    def resolve_forward_references(self) -> Type:
        body = self._body.resolve_forward_references()
        return Fix(self._var, body)

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
                IndividualKind(),
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
        rigid_variables: AbstractSet['_Variable'],
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

_x = BoundVariable(kind=IndividualKind())

float_type = ObjectType({}, nominal=True)
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


_int_type: Optional[Type] = None


def get_int_type() -> Type:
    assert _int_type is not None
    return _int_type


def set_int_type(ty: Type) -> None:
    global _int_type
    _int_type = ty


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
        {'__invert__': py_function_type[TypeSequence([]), _invert_result_var]},
    ),
)

_sub_operand_type = IndividualVariable()
_sub_result_type = IndividualVariable()
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

_add_other_operand_type = IndividualVariable()
_add_result_type = IndividualVariable()

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

bool_type = ObjectType({}, nominal=True)
bool_type.set_internal_name('bool_type')

# QUESTION: Allow comparison methods to return any object?

_other_type = IndividualVariable()
geq_comparable_type = GenericType(
    [_other_type],
    ObjectType(
        {'__ge__': py_function_type[TypeSequence([_other_type]), bool_type]},
    ),
)
geq_comparable_type.set_internal_name('geq_comparable_type')

leq_comparable_type = GenericType(
    [_other_type],
    ObjectType(
        {'__le__': py_function_type[TypeSequence([_other_type]), bool_type]},
    ),
)
leq_comparable_type.set_internal_name('leq_comparable_type')

lt_comparable_type = GenericType(
    [_other_type],
    ObjectType(
        {'__lt__': py_function_type[TypeSequence([_other_type]), bool_type]},
    ),
)
lt_comparable_type.set_internal_name('lt_comparable_type')

none_type = ObjectType({}, nominal=True)
none_type.set_internal_name('none_type')

_result_type = IndividualVariable()

iterator_type = GenericType(
    [_result_type],
    Fix(
        _x,
        ObjectType(
            {
                '__iter__': py_function_type[TypeSequence([]), _x],
                '__next__': py_function_type[
                    TypeSequence([none_type,]), _result_type
                ],
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

_optional_type_var = IndividualVariable()
optional_type = GenericType(
    [_optional_type_var], _OptionalType(_optional_type_var)
)
optional_type.set_internal_name('optional_type')

_key_type_var = IndividualVariable()
_value_type_var = IndividualVariable()
dict_type = ObjectType(
    {
        '__iter__': py_function_type[
            TypeSequence([]), iterator_type[_key_type_var,]
        ]
    },
    [_key_type_var, _value_type_var],
    nominal=True,
)
dict_type.set_internal_name('dict_type')

_start_type_var, _stop_type_var, _step_type_var = (
    IndividualVariable(),
    IndividualVariable(),
    IndividualVariable(),
)
slice_type = ObjectType(
    {}, [_start_type_var, _stop_type_var, _step_type_var], nominal=True
)
slice_type.set_internal_name('slice_type')

ellipsis_type = ObjectType({}, nominal=True)
not_implemented_type = ObjectType({}, nominal=True)

_element_types_var = SequenceVariable()
tuple_type = GenericType(
    [_element_types_var],
    ObjectType(
        {'__getitem__': py_function_type},
        nominal=True,
        # iterable_type is a structural supertype
    ),
    is_variadic=True,
)
tuple_type.set_internal_name('tuple_type')

base_exception_type = ObjectType({}, nominal=True)
module_type = ObjectType({}, nominal=True)

_index_type_var = IndividualVariable()
_result_type_var = IndividualVariable()
subscriptable_type = ObjectType(
    {
        '__getitem__': py_function_type[
            TypeSequence([_index_type_var]), _result_type_var
        ],
    },
    [_index_type_var, _result_type_var],
)

_answer_type_var = IndividualVariable()
continuation_monad_type = ObjectType(
    {}, [_result_type_var, _answer_type_var], nominal=True
)
continuation_monad_type.set_internal_name('continuation_monad_type')
