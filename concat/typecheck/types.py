from concat.orderedset import OrderedSet
from concat.typecheck import (
    AttributeError,
    StackMismatchError,
    TypeError,
)
import concat.typecheck
from typing import (
    AbstractSet,
    Optional,
    Dict,
    Iterable,
    Iterator,
    Sequence,
    Tuple,
    TypeVar,
    Union,
    List,
    Iterator,
    Set,
    Mapping,
    NoReturn,
    cast,
    overload,
    TYPE_CHECKING,
)
from typing_extensions import Literal
import abc
import collections.abc
from collections import defaultdict


if TYPE_CHECKING:
    from concat.typecheck import Environment, Substitutions


class Type(abc.ABC):
    # TODO: Fully replace with <=.
    def is_subtype_of(self, supertype: 'Type') -> bool:
        return (
            supertype is self
            or isinstance(self, IndividualType)
            and supertype is object_type
        )

    def __le__(self, other: object) -> bool:
        if not isinstance(other, Type):
            return NotImplemented
        return self.is_subtype_of(other)

    def __eq__(self, other: object) -> bool:
        if self is other:
            return True
        if not isinstance(other, Type):
            return NotImplemented
        return self <= other and other <= self

    def get_type_of_attribute(self, name: str) -> 'IndividualType':
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
    def free_type_variables(self) -> OrderedSet['_Variable']:
        pass

    @abc.abstractmethod
    def apply_substitution(
        self, _: 'concat.typecheck.Substitutions'
    ) -> 'Type':
        pass

    @abc.abstractmethod
    def constrain_and_bind_supertype_variables(
        self,
        supertype: 'Type',
        rigid_variables: AbstractSet['_Variable'],
        subtyping_assumptions: List[Tuple['IndividualType', 'IndividualType']],
    ) -> 'Substitutions':
        pass

    @abc.abstractmethod
    def constrain_and_bind_subtype_variables(
        self,
        supertype: 'Type',
        rigid_variables: AbstractSet['_Variable'],
        subtyping_assumptions: List[Tuple['IndividualType', 'IndividualType']],
    ) -> 'Substitutions':
        pass

    # QUESTION: Should I remove this? Should I not distinguish between subtype
    # and supertype variables in the other two constraint methods? I should
    # look bidirectional typing with polymorphism/generics. Maybe 'Complete and
    # Easy'?
    def constrain(self, supertype: 'Type') -> None:
        if not self.is_subtype_of(supertype):
            raise TypeError(
                '{} is not a subtype of {}'.format(self, supertype)
            )

    def instantiate(self) -> 'Type':
        return self


class IndividualType(Type, abc.ABC):
    def to_for_all(self) -> Type:
        return ForAll([], self)

    def is_subtype_of(self, supertype: Type) -> bool:
        if isinstance(supertype, _OptionalType):
            if (
                self == none_type
                or not supertype.type_arguments
                or isinstance(supertype.type_arguments[0], IndividualType)
                and self.is_subtype_of(supertype.type_arguments[0])
            ):
                return True
            return False
        return super().is_subtype_of(supertype)


class _Variable(Type, abc.ABC):
    """Objects that represent type variables.

    Every type variable object is assumed to be unique. Thus, fresh type
    variables can be made simply by creating new objects. They can also be
    compared by identity."""

    def apply_substitution(
        self, sub: 'concat.typecheck.Substitutions'
    ) -> Union[IndividualType, '_Variable', 'TypeSequence']:
        if self in sub:
            return sub[self]  # type: ignore
        return self

    def free_type_variables(self) -> OrderedSet['_Variable']:
        return OrderedSet({self})


class IndividualVariable(_Variable, IndividualType):
    def __init__(self) -> None:
        super().__init__()

    def constrain_and_bind_supertype_variables(
        self,
        supertype: Type,
        rigid_variables: AbstractSet['_Variable'],
        subtyping_assumptions: List[Tuple[IndividualType, IndividualType]],
    ) -> 'Substitutions':
        from concat.typecheck import Substitutions

        if self is supertype or supertype == object_type:
            return Substitutions()
        if not isinstance(supertype, IndividualType):
            raise TypeError(
                '{} must be an individual type: expected {}'.format(
                    supertype, self
                )
            )
        if self in rigid_variables:
            raise TypeError(
                '{} is considered fixed here and cannot become a subtype of {}'.format(
                    self, supertype
                )
            )
        if (
            isinstance(supertype, IndividualVariable)
            and supertype not in rigid_variables
        ):
            return Substitutions({supertype: self})
        # Let's not support bounded quantification or inferring the types of
        # named functions. Thus, the subtype constraint should fail here.
        raise TypeError(
            '{} is an individual type variable and cannot be a subtype of {}'.format(
                self, supertype
            )
        )

    def constrain_and_bind_subtype_variables(
        self,
        supertype: Type,
        rigid_variables: AbstractSet['_Variable'],
        subtyping_assumptions: List[Tuple[IndividualType, IndividualType]],
    ) -> 'Substitutions':
        from concat.typecheck import Substitutions

        if self is supertype:
            return Substitutions()
        if supertype == object_type:
            return Substitutions({self: object_type})
        if not isinstance(supertype, IndividualType):
            raise TypeError(
                '{} must be an individual type: expected {}'.format(
                    supertype, self
                )
            )
        if self in rigid_variables:
            raise TypeError(
                '{} is considered fixed here and cannot become a subtype of {}'.format(
                    self, supertype
                )
            )
        return Substitutions({self: supertype})

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
        raise TypeError(
            '{} is an individual type variable, so its attributes are unknown'.format(
                self
            )
        )


class SequenceVariable(_Variable):
    def __init__(self) -> None:
        super().__init__()

    def __str__(self) -> str:
        return '*t_{}'.format(id(self))

    def __hash__(self) -> int:
        return hash(id(self))

    def constrain_and_bind_supertype_variables(
        self,
        supertype: Type,
        rigid_variables: AbstractSet['_Variable'],
        subtyping_assumptions: List[Tuple['IndividualType', 'IndividualType']],
    ) -> 'Substitutions':
        from concat.typecheck import Substitutions

        if not isinstance(supertype, (SequenceVariable, TypeSequence)):
            raise TypeError(
                '{} must be a sequence type, not {}'.format(self, supertype)
            )
        if self in rigid_variables:
            raise Exception('todo')
        # occurs check
        if self is not supertype and self in supertype.free_type_variables():
            raise TypeError(
                '{} cannot be a subtype of {} because it appears in {}'.format(
                    self, supertype, supertype
                )
            )
        if isinstance(supertype, SequenceVariable):
            return Substitutions({supertype: self})
        return Substitutions()

    def constrain_and_bind_subtype_variables(
        self,
        supertype: Type,
        rigid_variables: AbstractSet['_Variable'],
        subtyping_assumptions: List[Tuple['IndividualType', 'IndividualType']],
    ) -> 'Substitutions':
        from concat.typecheck import Substitutions

        if not isinstance(supertype, (SequenceVariable, TypeSequence)):
            raise TypeError(
                '{} must be a sequence type, not {}'.format(self, supertype)
            )
        if self in rigid_variables:
            raise TypeError(
                '{} is fixed here and cannot become a subtype of another type'.format(
                    self
                )
            )
        # occurs check
        if self is not supertype and self in supertype.free_type_variables():
            raise TypeError(
                '{} cannot be a subtype of {} because it appears in {}'.format(
                    self, supertype, supertype
                )
            )
        return Substitutions({self: supertype})

    def get_type_of_attribute(self, name: str) -> NoReturn:
        raise TypeError(
            'the sequence type {} does not hold attributes'.format(self)
        )

    @property
    def attributes(self) -> NoReturn:
        raise TypeError(
            'the sequence type {} does not hold attributes'.format(self)
        )


class TypeSequence(Type, Iterable['StackItemType']):
    def __init__(self, sequence: Sequence['StackItemType']) -> None:
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
            subbed_type: Union[StackItemType, Sequence[StackItemType]] = sub(
                type
            )
            if isinstance(subbed_type, TypeSequence):
                subbed_types += [*subbed_type]
            else:
                subbed_types.append(subbed_type)
        return TypeSequence(subbed_types)

    def is_subtype_of(self, supertype: Type) -> bool:
        if (
            isinstance(supertype, SequenceVariable)
            and not self._individual_types
            and self._rest is supertype
        ):
            return True
        elif isinstance(supertype, TypeSequence):
            if self._is_empty() and supertype._is_empty():
                return True
            elif not self._individual_types:
                if (
                    self._rest
                    and supertype._rest
                    and not supertype._individual_types
                ):
                    return self._rest is supertype._rest
                else:
                    return False
            elif self._individual_types and supertype._individual_types:
                if (
                    not self._individual_types[-1]
                    <= supertype._individual_types[-1]
                ):
                    return False
                return self[:-1] <= supertype[:-1]
            else:
                return False
        else:
            raise TypeError(
                '{} must be a sequence type, not {}'.format(self, supertype)
            )

    def constrain_and_bind_supertype_variables(
        self,
        supertype: Type,
        rigid_variables: AbstractSet['_Variable'],
        subtyping_assumptions: List[Tuple['IndividualType', 'IndividualType']],
    ) -> 'Substitutions':
        """Check that self is a subtype of supertype.

        Free type variables that appear in the supertype type sequence are set
        to be equal to their counterparts in the subtype sequence so that type
        information can be propagated into calls of named functions.
        """
        from concat.typecheck import Substitutions

        if isinstance(supertype, SequenceVariable):
            supertype = TypeSequence([supertype])

        if isinstance(supertype, TypeSequence):
            if self._is_empty() and supertype._is_empty():
                return Substitutions()
            elif (
                self._is_empty()
                and supertype._rest
                and not supertype._individual_types
                and supertype._rest not in rigid_variables
            ):
                return Substitutions({supertype._rest: self})
            elif (
                supertype._is_empty()
                and self._rest
                and not self._individual_types
            ):
                raise StackMismatchError(self, supertype)
            elif not self._individual_types:
                if (
                    self._is_empty()
                    and supertype._is_empty()
                    or self._rest is supertype._rest
                ):
                    return Substitutions()
                if (
                    self._rest
                    and supertype._rest
                    and not supertype._individual_types
                    and supertype._rest not in rigid_variables
                ):
                    return Substitutions({supertype._rest: self._rest})
                elif (
                    self._is_empty()
                    and supertype._rest
                    and not supertype._individual_types
                    and supertype._rest not in rigid_variables
                ):
                    return Substitutions({supertype._rest: self})
                else:
                    raise StackMismatchError(self, supertype)
            elif (
                not supertype._individual_types
                and supertype._rest
                and supertype._rest not in self.free_type_variables()
                and supertype._rest not in rigid_variables
            ):
                return Substitutions({supertype._rest: self})
            elif self._individual_types and supertype._individual_types:
                sub = self._individual_types[
                    -1
                ].constrain_and_bind_supertype_variables(
                    supertype._individual_types[-1],
                    rigid_variables,
                    subtyping_assumptions,
                )
                # constrain individual variables in the second sequence type to
                # be *equal* to the corresponding type in the first sequence
                # type.
                is_variable = isinstance(
                    supertype._individual_types[-1], IndividualVariable
                )
                if (
                    is_variable
                    and supertype._individual_types[-1] not in rigid_variables
                ):
                    sub = Substitutions(
                        {
                            supertype._individual_types[
                                -1
                            ]: self._individual_types[-1]
                        }
                    )(sub)
                try:
                    sub = sub(
                        self[:-1]
                    ).constrain_and_bind_supertype_variables(
                        sub(supertype[:-1]),
                        rigid_variables,
                        subtyping_assumptions,
                    )(
                        sub
                    )
                    return sub
                except StackMismatchError:
                    raise StackMismatchError(self, supertype)
            else:
                # TODO: Add info about occurs check and rigid variables.
                raise StackMismatchError(self, supertype)
        else:
            raise TypeError(
                '{} must be a sequence type, not {}'.format(self, supertype)
            )

    def constrain_and_bind_subtype_variables(
        self,
        supertype: Type,
        rigid_variables: AbstractSet['_Variable'],
        subtyping_assumptions: List[Tuple['IndividualType', 'IndividualType']],
    ) -> 'Substitutions':
        from concat.typecheck import Substitutions

        if isinstance(supertype, SequenceVariable):
            supertype = TypeSequence([supertype])

        if isinstance(supertype, TypeSequence):
            if self._is_empty() and supertype._is_empty():
                return Substitutions()
            elif (
                self._is_empty()
                and supertype._rest
                and not supertype._individual_types
                and supertype._rest not in rigid_variables
            ):
                raise StackMismatchError(self, supertype)
            elif (
                supertype._is_empty()
                and self._rest
                and not self._individual_types
                and self._rest not in rigid_variables
            ):
                return Substitutions({self._rest: supertype})
            elif not self._individual_types:
                if (
                    self._is_empty()
                    and supertype._is_empty()
                    or self._rest is supertype._rest
                ):
                    return Substitutions()
                if (
                    self._rest
                    and self._rest not in rigid_variables
                    and self._rest not in supertype.free_type_variables()
                ):
                    return Substitutions({self._rest: supertype})
                elif (
                    self._is_empty()
                    and supertype._rest
                    and not supertype._individual_types
                ):
                    # QUESTION: Should this be allowed? I'm being defensive here.
                    raise StackMismatchError(self, supertype)
                else:
                    raise StackMismatchError(self, supertype)
            elif (
                not supertype._individual_types
                and supertype._rest
                and supertype._rest not in self.free_type_variables()
                and supertype._rest not in rigid_variables
            ):
                raise StackMismatchError(self, supertype)
            elif self._individual_types and supertype._individual_types:
                sub = self._individual_types[
                    -1
                ].constrain_and_bind_subtype_variables(
                    supertype._individual_types[-1],
                    rigid_variables,
                    subtyping_assumptions,
                )
                is_variable = isinstance(
                    self._individual_types[-1], IndividualVariable
                )
                if (
                    is_variable
                    and self._individual_types[-1] not in rigid_variables
                ):
                    sub = Substitutions(
                        {
                            self._individual_types[
                                -1
                            ]: supertype._individual_types[-1]
                        }
                    )(sub)
                try:
                    sub = sub(self[:-1]).constrain_and_bind_subtype_variables(
                        sub(supertype[:-1]),
                        rigid_variables,
                        subtyping_assumptions,
                    )(sub)
                    return sub
                except StackMismatchError:
                    raise StackMismatchError(self, supertype)
            else:
                raise StackMismatchError(self, supertype)
        else:
            raise TypeError(
                '{} must be a sequence type, not {}'.format(self, supertype)
            )

    def free_type_variables(self) -> OrderedSet['_Variable']:
        ftv: OrderedSet[_Variable] = OrderedSet([])
        for t in self:
            ftv |= t.free_type_variables()
        return ftv

    @property
    def attributes(self) -> NoReturn:
        raise TypeError(
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


# TODO: Actually get rid of ForAll uses. This is a temporary measure since I
# don't want to do that work right now.
def ForAll(type_parameters: Sequence['_Variable'], type: Type) -> Type:
    return ObjectType(IndividualVariable(), type.attributes, type_parameters,)


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
        return ObjectType(
            IndividualVariable(),
            {'__call__': self,},
            list(self.free_type_variables() - gamma.free_type_variables()),
        )

    def __hash__(self) -> int:
        # FIXME: Alpha equivalence
        return hash((self.input, self.output))

    def is_subtype_of(
        self,
        supertype: Type,
        _sub: Optional['concat.typecheck.Substitutions'] = None,
    ) -> bool:
        if super().is_subtype_of(supertype):
            return True
        if isinstance(supertype, _Function):
            if len(tuple(self.input)) != len(tuple(supertype.input)) or len(
                tuple(self.output)
            ) != len(tuple(supertype.output)):
                return False
            # Sequence variables are handled through renaming.
            if _sub is None:
                _sub = concat.typecheck.Substitutions()
            input_rename_result = self._rename_sequence_variable(
                tuple(self.input), tuple(supertype.input), _sub
            )
            output_rename_result = self._rename_sequence_variable(
                tuple(supertype.output), tuple(self.output), _sub
            )
            if not (input_rename_result and output_rename_result):
                return False
            # TODO: What about individual type variables. We should be careful
            # with renaming those, too.
            # input types are contravariant
            for type_from_self, type_from_supertype in zip(
                self.input, supertype.input
            ):
                type_from_self, type_from_supertype = (
                    cast(StackItemType, _sub(type_from_self)),
                    cast(StackItemType, _sub(type_from_supertype)),
                )
                if isinstance(type_from_supertype, _Function):
                    if not type_from_supertype.is_subtype_of(
                        type_from_self, _sub
                    ):
                        return False
                elif not type_from_supertype.is_subtype_of(type_from_self):
                    return False
            # output types are covariant
            for type_from_self, type_from_supertype in zip(
                self.output, supertype.output
            ):
                type_from_self, type_from_supertype = (
                    cast(StackItemType, _sub(type_from_self)),
                    cast(StackItemType, _sub(type_from_supertype)),
                )
                if isinstance(type_from_self, _Function):
                    if not type_from_self.is_subtype_of(
                        type_from_supertype, _sub
                    ):
                        return False
                elif not type_from_self.is_subtype_of(type_from_supertype):
                    return False
            return True
        return False

    def constrain_and_bind_supertype_variables(
        self,
        supertype: Type,
        rigid_variables: AbstractSet['_Variable'],
        subtyping_assumptions: List[Tuple[IndividualType, IndividualType]],
    ) -> 'Substitutions':
        from concat.typecheck import Substitutions

        if (
            isinstance(supertype, IndividualVariable)
            and supertype not in rigid_variables
        ):
            return Substitutions({supertype: self})
        if not isinstance(supertype, StackEffect):
            raise TypeError(
                '{} is not a subtype of {}'.format(self, supertype)
            )
        # Remember that the input should be contravariant!
        # QUESTION: Constrain the supertype variables here during contravariance check?
        sub = supertype.input.constrain_and_bind_subtype_variables(
            self.input, rigid_variables, subtyping_assumptions
        )
        sub = sub(self.output).constrain_and_bind_supertype_variables(
            sub(supertype.output), rigid_variables, subtyping_assumptions
        )(sub)
        return sub

    def constrain_and_bind_subtype_variables(
        self,
        supertype: Type,
        rigid_variables: AbstractSet['_Variable'],
        subtyping_assumptions: List[Tuple[IndividualType, IndividualType]],
    ) -> 'Substitutions':
        if not isinstance(supertype, StackEffect):
            raise TypeError(
                '{} is not a subtype of {}'.format(self, supertype)
            )
        # Remember that the input should be contravariant!
        # QUESTION: Constrain the supertype variables here during contravariance check?
        sub = supertype.input.constrain_and_bind_supertype_variables(
            self.input, rigid_variables, subtyping_assumptions
        )
        sub = sub(self.output).constrain_and_bind_subtype_variables(
            sub(supertype.output), rigid_variables, subtyping_assumptions
        )(sub)
        return sub

    def free_type_variables(self) -> OrderedSet['_Variable']:
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
                sub[supertype_list[0]] = subtype_list[0]
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


class QuotationType(_Function):
    def __init__(self, fun_type: _Function) -> None:
        super().__init__(fun_type.input, fun_type.output)

    def is_subtype_of(
        self,
        supertype: Type,
        _sub: Optional['concat.typecheck.Substitutions'] = None,
    ) -> bool:
        if super().is_subtype_of(supertype, _sub):
            return True
        if supertype == iterable_type:
            return True
        return False

    def constrain_and_bind_supertype_variables(
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
            return quotation_iterable_type.constrain_and_bind_supertype_variables(
                supertype, rigid_variables, subtyping_assumptions
            )
        return super().constrain_and_bind_supertype_variables(
            supertype, rigid_variables, subtyping_assumptions
        )

    def constrain_and_bind_subtype_variables(
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
            return quotation_iterable_type.constrain_and_bind_subtype_variables(
                supertype, rigid_variables, subtyping_assumptions
            )
        return super().constrain_and_bind_subtype_variables(
            supertype, rigid_variables, subtyping_assumptions
        )

    def apply_substitution(
        self, sub: 'concat.typecheck.Substitutions'
    ) -> 'QuotationType':
        return QuotationType(super().apply_substitution(sub))


StackItemType = Union[SequenceVariable, IndividualType]


def free_type_variables_of_mapping(
    attributes: Mapping[str, Type]
) -> OrderedSet[_Variable]:
    ftv: OrderedSet[_Variable] = OrderedSet([])
    for sigma in attributes.values():
        ftv |= sigma.free_type_variables()
    return ftv


def init_primitives():
    pass


TypeArguments = Sequence[Union[StackItemType, TypeSequence]]
_T = TypeVar('_T')


class ObjectType(IndividualType):
    """The representation of types of objects, based on a gradual typing paper.

    That paper is "Design and Evaluation of Gradual Typing for Python"
    (Vitousek et al. 2014)."""

    def __init__(
        self,
        self_type: IndividualVariable,
        # Attributes can be universally quantified since ObjectType allows it.
        attributes: Dict[str, IndividualType],
        type_parameters: Sequence[_Variable] = (),
        nominal_supertypes: Sequence[IndividualType] = (),
        nominal: bool = False,
        _type_arguments: TypeArguments = (),
        _head: Optional['ObjectType'] = None,
        **_other_kwargs,
    ) -> None:
        # There should be no need to make the self_type variable unique because
        # it is treated as a bound variable in apply_substitution. In other
        # words, it is removed from any substitution received.
        self._self_type = self_type

        self._attributes = attributes

        self._type_parameters = type_parameters
        self._nominal_supertypes = nominal_supertypes
        self._nominal = nominal

        self._type_arguments: TypeArguments = _type_arguments

        self._head = _head or self

        self._internal_name: Optional[str] = None
        self._internal_name = self._head._internal_name

        self._other_kwargs = _other_kwargs.copy()
        if '_type_arguments' in self._other_kwargs:
            del self._other_kwargs['_type_arguments']
        if 'nominal' in self._other_kwargs:
            del self._other_kwargs['nominal']

        self._instantiations: Dict[TypeArguments, ObjectType] = {}

    def apply_substitution(
        self,
        sub: 'concat.typecheck.Substitutions',
        _should_quantify_over_type_parameters=True,
    ) -> 'ObjectType':
        from concat.typecheck import Substitutions

        if _should_quantify_over_type_parameters:
            sub = Substitutions(
                {
                    a: i
                    for a, i in sub.items()
                    # Don't include self_type in substitution, it is bound.
                    if a not in self._type_parameters
                    and a is not self._self_type
                }
            )
            # if no free type vars will be substituted, just return self
            if not any(
                free_var in sub for free_var in self.free_type_variables()
            ):
                return self
        else:
            sub = Substitutions(
                {a: i for a, i in sub.items() if a is not self._self_type}
            )
            # if no free type vars will be substituted, just return self
            if not any(
                free_var in sub
                for free_var in {
                    *self.free_type_variables(),
                    *self._type_parameters,
                }
            ):
                return self
        attributes = cast(
            Dict[str, IndividualType],
            {attr: sub(t) for attr, t in self._attributes.items()},
        )
        nominal_supertypes = [
            sub(supertype) for supertype in self._nominal_supertypes
        ]
        type_arguments = [
            cast(Union[StackItemType, TypeSequence], sub(type_argument))
            for type_argument in self._type_arguments
        ]
        subbed_type = type(self)(
            self._self_type,
            attributes,
            type_parameters=self._type_parameters,
            nominal_supertypes=nominal_supertypes,
            nominal=self._nominal,
            _type_arguments=type_arguments,
            # head is only used to keep track of where a type came from, so
            # there's no need to substitute it
            _head=self._head,
            **self._other_kwargs,
        )
        if self._internal_name is not None:
            subbed_type.set_internal_name(self._internal_name)
        return subbed_type

    def is_subtype_of(self, supertype: 'Type') -> bool:
        from concat.typecheck import Substitutions

        if supertype in self._nominal_supertypes or self is supertype:
            return True
        if isinstance(supertype, (_Function, PythonFunctionType)):
            if '__call__' not in self._attributes:
                return False
            return self._attributes['__call__'] <= supertype
        if not isinstance(supertype, ObjectType):
            return super().is_subtype_of(supertype)
        if self._arity != supertype._arity:
            return False
        if self._arity == 0 and supertype is object_type:
            return True
        if supertype._nominal and self._head is not supertype._head:
            return False
        # instantiate these types in a way such that alpha equivalence is not
        # an issue
        # NOTE: I assume the parameters are in the same order, which is
        # fragile.
        parameter_pairs = zip(self.type_parameters, supertype.type_parameters)
        if not all(type(a) == type(b) for a, b in parameter_pairs):
            return False
        self = self.instantiate()
        supertype = supertype.instantiate()
        parameter_sub = Substitutions(
            {
                **dict(zip(self.type_arguments, supertype.type_arguments)),
                self.self_type: supertype.self_type,
            }
        )
        self = parameter_sub(self)

        for attr, attr_type in supertype._attributes.items():
            if attr not in self._attributes:
                return False
            sub = concat.typecheck.Substitutions(
                {self._self_type: supertype._self_type}
            )
            if not (
                cast(IndividualType, sub(self._attributes[attr])) <= attr_type
            ):
                return False
        return True

    def constrain_and_bind_supertype_variables(
        self,
        supertype: Type,
        rigid_variables: AbstractSet['_Variable'],
        subtyping_assumptions: List[Tuple[IndividualType, IndividualType]],
    ) -> 'Substitutions':
        from concat.typecheck import Substitutions

        if (self, supertype) in subtyping_assumptions:
            return Substitutions()

        if (
            isinstance(supertype, IndividualVariable)
            and supertype not in rigid_variables
        ):
            return Substitutions({supertype: self})
        elif isinstance(supertype, (SequenceVariable, TypeSequence)):
            raise TypeError(
                '{} is an individual type, but {} is a sequence type'.format(
                    self, supertype
                )
            )

        # To support higher-rank polymorphism, polymorphic types are subtypes
        # of their instances.

        if isinstance(supertype, StackEffect):
            subtyping_assumptions.append((self, supertype))

            instantiated_self = self.instantiate()
            # We know instantiated_self is not a type constructor here, so
            # there's no need to worry about variable binding
            return instantiated_self.get_type_of_attribute(
                '__call__'
            ).constrain_and_bind_supertype_variables(
                supertype, rigid_variables, subtyping_assumptions
            )
        if not isinstance(supertype, ObjectType):
            raise NotImplementedError(supertype)
        if self._arity < supertype._arity:
            raise TypeError(
                '{} is not as polymorphic as {}'.format(self, supertype)
            )
        # every object type is a subtype of object_type
        if supertype == object_type:
            return Substitutions()
        # Don't forget that there's nominal subtyping too.
        if supertype._nominal:
            if (
                supertype not in self._nominal_supertypes
                and supertype != self
                and self._head != supertype._head
            ):
                raise TypeError(
                    '{} is not a subtype of {}'.format(self, supertype)
                )

        subtyping_assumptions.append((self, supertype))

        # constraining to an optional type
        if (
            supertype._head == optional_type
            and supertype._arity == 0
            and self._arity == 0
        ):
            try:
                return self.constrain_and_bind_supertype_variables(
                    none_type, rigid_variables, subtyping_assumptions
                )
            except TypeError:
                return self.constrain_and_bind_supertype_variables(
                    supertype._type_arguments[0],
                    rigid_variables,
                    subtyping_assumptions,
                )

        # don't constrain the type arguments, constrain those based on
        # the attributes
        sub = Substitutions()
        # We must not bind any type parameters in self or supertype! To support
        # higher-rank polymorphism, let's instantiate both types. At this
        # point, self should be at least as polymorphic as supertype.
        assert self._arity >= supertype._arity
        instantiated_self = self.instantiate()
        supertype = supertype.instantiate()
        for name in supertype._attributes:
            type = instantiated_self.get_type_of_attribute(name)
            sub = sub(type).constrain_and_bind_supertype_variables(
                sub(supertype.get_type_of_attribute(name)),
                rigid_variables,
                subtyping_assumptions,
            )(sub)
        return sub

    def constrain_and_bind_subtype_variables(
        self,
        supertype: Type,
        rigid_variables: AbstractSet['_Variable'],
        subtyping_assumptions: List[Tuple[IndividualType, IndividualType]],
    ) -> 'Substitutions':
        from concat.typecheck import Substitutions

        if (self, supertype) in subtyping_assumptions:
            return Substitutions()

        if isinstance(supertype, IndividualVariable):
            raise TypeError(
                '{} is unknown here and cannot be a supertype of {}'.format(
                    supertype, self
                )
            )
        elif isinstance(supertype, (SequenceVariable, TypeSequence)):
            raise TypeError(
                '{} is an individual type, but {} is a sequence type'.format(
                    self, supertype
                )
            )

        # To support higher-rank polymorphism, polymorphic types are subtypes
        # of their instances.

        if isinstance(supertype, StackEffect):
            subtyping_assumptions.append((self, supertype))

            instantiated_self = self.instantiate()
            # We know self is not a type constructor here, so there's no need
            # to worry about variable binding
            return instantiated_self.get_type_of_attribute(
                '__call__'
            ).constrain_and_bind_subtype_variables(
                supertype, rigid_variables, subtyping_assumptions
            )
        if not isinstance(supertype, ObjectType):
            raise NotImplementedError(supertype)
        if self._arity < supertype._arity:
            raise TypeError(
                '{} is not as polymorphic as {}'.format(self, supertype)
            )
        # every object type is a subtype of object_type
        if supertype == object_type:
            return Substitutions()
        # Don't forget that there's nominal subtyping too.
        if supertype._nominal:
            if (
                supertype not in self._nominal_supertypes
                and supertype != self
                and self._head != supertype._head
            ):
                raise TypeError(
                    '{} is not a subtype of {}'.format(self, supertype)
                )

        subtyping_assumptions.append((self, supertype))

        # constraining to an optional type
        if (
            supertype._head == optional_type
            and supertype._arity == 0
            and self._arity == 0
        ):
            try:
                return self.constrain_and_bind_subtype_variables(
                    none_type, rigid_variables, subtyping_assumptions
                )
            except TypeError:
                return self.constrain_and_bind_subtype_variables(
                    supertype._type_arguments[0],
                    rigid_variables,
                    subtyping_assumptions,
                )

        # don't constrain the type arguments, constrain those based on
        # the attributes
        sub = Substitutions()
        # We must not bind any type parameters in self or supertype! To support
        # higher-rank polymorphism, let's instantiate both types. At this
        # point, self should be at least as polymorphic as supertype.
        assert self._arity >= supertype._arity
        instantiated_self = self.instantiate()
        supertype = supertype.instantiate()
        for name in supertype._attributes:
            type = instantiated_self.get_type_of_attribute(name)
            sub = type.constrain_and_bind_subtype_variables(
                supertype.get_type_of_attribute(name),
                rigid_variables,
                subtyping_assumptions,
            )(sub)
        return sub

    def get_type_of_attribute(self, attribute: str) -> IndividualType:
        if attribute not in self._attributes:
            raise AttributeError(self, attribute)

        self_sub = concat.typecheck.Substitutions({self._self_type: self})

        return self_sub(self._attributes[attribute])

    def __repr__(self) -> str:
        return '{}({!r}, {!r}, {!r}, {!r}, {!r}, {!r}, {!r})'.format(
            type(self).__qualname__,
            self._self_type,
            self._attributes,
            self._type_parameters,
            self._nominal_supertypes,
            self._nominal,
            self._type_arguments,
            None if self._head is self else self._head,
        )

    def free_type_variables(self) -> OrderedSet[_Variable]:
        ftv = free_type_variables_of_mapping(self.attributes)
        for arg in self.type_arguments:
            ftv |= arg.free_type_variables()
        # QUESTION: Include supertypes?
        ftv -= {self.self_type, *self.type_parameters}
        return ftv

    def __str__(self) -> str:
        if self._internal_name is not None:
            if len(self._type_arguments) > 0:
                return (
                    self._internal_name
                    + '['
                    + ', '.join(map(str, self._type_arguments))
                    + ']'
                )
            return self._internal_name
        assert self._internal_name is None
        return '{}({}, {}, {}, {}, {}, {}, {})'.format(
            type(self).__qualname__,
            self._self_type,
            _mapping_to_str(self._attributes),
            _iterable_to_str(self._type_parameters),
            _iterable_to_str(self._nominal_supertypes),
            self._nominal,
            _iterable_to_str(self._type_arguments),
            None if self._head is self else self._head,
        )

    def set_internal_name(self, name: str) -> None:
        self._internal_name = name

    _hash_variable = None

    def __hash__(self) -> int:
        from concat.typecheck import Substitutions

        if ObjectType._hash_variable is None:
            ObjectType._hash_variable = IndividualVariable()
        sub = Substitutions({self._self_type: ObjectType._hash_variable})
        type_to_hash = sub(self)
        return hash(
            (
                tuple(type_to_hash._attributes.items()),
                tuple(type_to_hash._type_parameters),
                tuple(type_to_hash._nominal_supertypes),
                type_to_hash._nominal,
                # FIXME: I get 'not hashable' errors about this.
                # tuple(type_to_hash._type_arguments),
                None if type_to_hash._head == self else type_to_hash._head,
            )
        )

    def __getitem__(
        self, type_arguments: Sequence[StackItemType]
    ) -> 'ObjectType':
        from concat.typecheck import Substitutions

        if self._arity != len(type_arguments):
            raise TypeError(
                'type constructor {} given {} arguments, expected {} arguments'.format(
                    self, len(type_arguments), self._arity
                )
            )

        type_arguments = tuple(type_arguments)
        if type_arguments in self._instantiations:
            return self._instantiations[type_arguments]

        sub = Substitutions(zip(self._type_parameters, type_arguments))
        result = self.apply_substitution(
            sub, _should_quantify_over_type_parameters=False
        )
        # HACK: We remove the parameters and add arguments through mutation.
        result._type_parameters = ()
        result._type_arguments = type_arguments

        self._instantiations[type_arguments] = result

        return result

    def instantiate(self: _T) -> _T:
        # Avoid overwriting the type arguments if type is already instantiated.
        if self._arity == 0:
            return self
        fresh_variables = [type(a)() for a in self._type_parameters]
        return self[fresh_variables]

    @property
    def attributes(self) -> Dict[str, IndividualType]:
        return self._attributes

    @property
    def self_type(self) -> IndividualVariable:
        return self._self_type

    @property
    def type_arguments(self) -> TypeArguments:
        return self._type_arguments

    @property
    def head(self) -> 'ObjectType':
        return self._head

    @property
    def type_parameters(self) -> Sequence[_Variable]:
        return self._type_parameters

    @property
    def nominal_supertypes(self) -> Sequence[IndividualType]:
        return self._nominal_supertypes

    @property
    def _arity(self) -> int:
        return len(self._type_parameters)


class ClassType(ObjectType):
    """The representation of types of classes, like in "Design and Evaluation of Gradual Typing for Python" (Vitousek et al. 2014)."""

    def is_subtype_of(self, supertype: Type) -> bool:
        if (
            not supertype.has_attribute('__call__')
            or '__init__' not in self._attributes
        ):
            return super().is_subtype_of(supertype)
        bound_init = self._attributes['__init__'].bind()
        return bound_init <= supertype


class PythonFunctionType(ObjectType):
    def __init__(
        self,
        self_type: IndividualVariable,
        *args,
        _overloads: Sequence[
            Tuple[Sequence[StackItemType], IndividualType]
        ] = (),
        type_parameters=(),
        **kwargs,
    ) -> None:
        self._kwargs = kwargs.copy()
        # HACK: I shouldn't have to manipulate arguments like this
        if 'type_parameters' in self._kwargs:
            del self._kwargs['type_parameters']
        super().__init__(
            self_type,
            *args,
            **self._kwargs,
            _overloads=_overloads,
            type_parameters=type_parameters,
        )
        assert (
            self._arity == 0
            and len(self._type_arguments) == 2
            or self._arity == 2
            and len(self._type_arguments) == 0
        )
        if self._arity == 0:
            assert isinstance(self.input, collections.abc.Sequence)
        self._args = list(args)
        self._overloads = _overloads
        if '_head' in self._kwargs:
            del self._kwargs['_head']
        self._head: PythonFunctionType

    def __str__(self) -> str:
        if not self._type_arguments:
            return 'py_function_type'
        return 'py_function_type[{}, {}]'.format(
            _iterable_to_str(self.input), self.output
        )

    def get_type_of_attribute(self, attribute: str) -> IndividualType:
        from concat.typecheck import Substitutions

        sub = Substitutions({self._self_type: self})
        if attribute == '__call__':
            return self
        else:
            return super().get_type_of_attribute(attribute)

    def __getitem__(
        self, arguments: Tuple[TypeSequence, IndividualType]
    ) -> 'PythonFunctionType':
        assert self._arity == 2
        input = arguments[0]
        output = arguments[1]
        return PythonFunctionType(
            self._self_type,
            *self._args,
            **{
                **self._kwargs,
                '_type_arguments': (input, output),
                'type_parameters': (),
            },
            _overloads=[],
            _head=self,
        )

    def apply_substitution(
        self, sub: 'concat.typecheck.Substitutions'
    ) -> 'PythonFunctionType':
        if self._arity == 0:
            type = py_function_type[
                sub(TypeSequence(self.input)), sub(self.output)
            ]
            for overload in self._overloads:
                # This is one of the few places where a type should be mutated.
                type._add_overload(
                    [sub(i) for i in overload[0]], sub(overload[1])
                )
            return type
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
        assert isinstance(self._type_arguments[1], IndividualType)
        return self._type_arguments[1]

    def select_overload(
        self, input_types: Sequence[StackItemType]
    ) -> Tuple['PythonFunctionType', 'Substitutions']:
        for overload in [(self.input, self.output), *self._overloads]:
            try:
                sub = TypeSequence(
                    input_types
                ).constrain_and_bind_supertype_variables(
                    TypeSequence(overload[0]), set(), []
                )
            except TypeError:
                continue
            return (
                sub(py_function_type[TypeSequence(overload[0]), overload[1]]),
                sub,
            )
        raise TypeError(
            'no overload of {} matches types {}'.format(self, input_types)
        )

    def with_overload(
        self, input: Sequence[StackItemType], output: IndividualType
    ) -> 'PythonFunctionType':
        return PythonFunctionType(
            self._self_type,
            *self._args,
            **self._kwargs,
            _overloads=[*self._overloads, (input, output)],
            _head=py_function_type,
        )

    def _add_overload(
        self, input: Sequence[StackItemType], output: IndividualType
    ) -> None:
        self._overloads.append((input, output))

    def bind(self) -> 'PythonFunctionType':
        assert self._arity == 0
        inputs = self.input[1:]
        output = self.output
        return self._head[TypeSequence(inputs), output]

    def is_subtype_of(self, supertype: Type) -> bool:
        if isinstance(supertype, PythonFunctionType):
            # NOTE: make sure types are of same kind (arity)
            if len(self._type_parameters) != len(supertype._type_parameters):
                return False
            if len(self._type_parameters) == 2:
                # both are py_function_type
                return True
            assert isinstance(supertype._type_arguments[0], TypeSequence)
            assert isinstance(self._type_arguments[1], IndividualType)
            return (
                supertype._type_arguments[0] <= self._type_arguments[0]
                and self._type_arguments[1] <= supertype._type_arguments[1]
            )
        else:
            return super().is_subtype_of(supertype)

    def constrain_and_bind_supertype_variables(
        self,
        supertype: Type,
        rigid_variables: AbstractSet['_Variable'],
        subtyping_assumptions: List[Tuple[IndividualType, IndividualType]],
    ) -> 'Substitutions':
        from concat.typecheck import Substitutions

        sub = super().constrain_and_bind_supertype_variables(
            supertype, rigid_variables, subtyping_assumptions
        )

        if (
            isinstance(supertype, PythonFunctionType)
            and supertype._arity <= self._arity
        ):
            instantiated_self = self.instantiate()
            supertype = supertype.instantiate()

            # ObjectType constrains the attributes, not the type arguments
            # directly, so we'll doo that here. This isn't problematic because
            # we know the variance of the arguments here.

            # No need to extend the rigid variables, we know both types have no
            # parameters at this point.

            # Support overloading the subtype.
            for overload in [
                (instantiated_self.input, instantiated_self.output),
                *instantiated_self._overloads,
            ]:
                try:
                    subtyping_assumptions_copy = subtyping_assumptions[:]
                    self_input_types = TypeSequence(overload[0])
                    supertype_input_types = TypeSequence(supertype.input)
                    sub = supertype_input_types.constrain_and_bind_subtype_variables(
                        self_input_types,
                        rigid_variables,
                        subtyping_assumptions_copy,
                    )(
                        sub
                    )
                    sub = sub(
                        instantiated_self.output
                    ).constrain_and_bind_supertype_variables(
                        sub(supertype.output),
                        rigid_variables,
                        subtyping_assumptions_copy,
                    )(
                        sub
                    )
                except TypeError:
                    continue
                finally:
                    subtyping_assumptions[:] = subtyping_assumptions_copy
                    return sub

        raise TypeError(
            'no overload of {} is a subtype of {}'.format(self, supertype)
        )

    def constrain_and_bind_subtype_variables(
        self,
        supertype: Type,
        rigid_variables: AbstractSet['_Variable'],
        subtyping_assumptions: List[Tuple[IndividualType, IndividualType]],
    ) -> 'Substitutions':
        from concat.typecheck import Substitutions

        sub = super().constrain_and_bind_subtype_variables(
            supertype, rigid_variables, subtyping_assumptions
        )

        if (
            isinstance(supertype, PythonFunctionType)
            and supertype._arity <= self._arity
        ):
            instantiated_self = self.instantiate()
            supertype = supertype.instantiate()

            # ObjectType constrains the attributes, not the type arguments
            # directly, so we'll doo that here. This isn't problematic because
            # we know the variance of the arguments here.

            for overload in [
                (instantiated_self.input, instantiated_self.output),
                *instantiated_self._overloads,
            ]:
                try:
                    subtyping_assumptions_copy = subtyping_assumptions[:]
                    self_input_types = TypeSequence(overload[0])
                    supertype_input_types = TypeSequence(supertype.input)
                    sub = supertype_input_types.constrain_and_bind_supertype_variables(
                        self_input_types,
                        rigid_variables,
                        subtyping_assumptions_copy,
                    )(
                        sub
                    )
                    sub = sub(
                        instantiated_self.output
                    ).constrain_and_bind_subtype_variables(
                        sub(supertype.output),
                        rigid_variables,
                        subtyping_assumptions_copy,
                    )(
                        sub
                    )
                except TypeError:
                    continue
                finally:
                    subtyping_assumptions[:] = subtyping_assumptions_copy
                    return sub

        raise TypeError(
            'no overload of {} is a subtype of {}'.format(self, supertype)
        )


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


class _OptionalType(ObjectType):
    def __init__(self, _type_arguments=[]) -> None:
        x = IndividualVariable()
        type_var = IndividualVariable()
        if len(_type_arguments) > 0:
            super().__init__(x, {}, [], _type_arguments=_type_arguments)
        else:
            super().__init__(x, {}, [type_var])

    def __getitem__(
        self, type_arguments: Sequence[StackItemType]
    ) -> '_OptionalType':
        assert len(type_arguments) == 1
        return _OptionalType(type_arguments)

    def apply_substitution(
        self, sub: 'concat.typecheck.Substitutions'
    ) -> '_OptionalType':
        # FIXME: self._type_arguments might not be a valid stack type.
        return _OptionalType(tuple(sub(TypeSequence(self._type_arguments))))


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
object_type = ObjectType(_x, {}, nominal=True)
object_type.set_internal_name('object_type')

_arg_type_var = SequenceVariable()
_return_type_var = IndividualVariable()
py_function_type = PythonFunctionType(
    _x, {}, type_parameters=[_arg_type_var, _return_type_var]
)
py_function_type.set_internal_name('py_function_type')

_invert_result_var = IndividualVariable()
invertible_type = ObjectType(
    _x,
    {'__invert__': py_function_type[TypeSequence([]), _invert_result_var]},
    [_invert_result_var],
)

_sub_operand_type = IndividualVariable()
_sub_result_type = IndividualVariable()
# FIXME: Add reverse_substractable_type for __rsub__
subtractable_type = ObjectType(
    _x,
    {
        '__sub__': py_function_type[
            TypeSequence([_sub_operand_type]), _sub_result_type
        ]
    },
    [_sub_operand_type, _sub_result_type],
)

_add_result_type = IndividualVariable()

addable_type = ObjectType(
    _x,
    {
        '__add__': py_function_type[
            TypeSequence([object_type]), _add_result_type
        ]
    },
    [_add_result_type],
)
addable_type.set_internal_name('addable_type')

bool_type = ObjectType(_x, {}, nominal=True)
bool_type.set_internal_name('bool_type')

# QUESTION: Allow comparison methods to return any object?

_other_type = IndividualVariable()
geq_comparable_type = ObjectType(
    _x,
    {'__ge__': py_function_type[TypeSequence([_other_type]), bool_type]},
    [_other_type],
)
geq_comparable_type.set_internal_name('geq_comparable_type')

leq_comparable_type = ObjectType(
    _x,
    {'__le__': py_function_type[TypeSequence([_other_type]), bool_type]},
    [_other_type],
)
leq_comparable_type.set_internal_name('leq_comparable_type')

lt_comparable_type = ObjectType(
    _x,
    {'__lt__': py_function_type[TypeSequence([_other_type]), bool_type]},
    [_other_type],
)
lt_comparable_type.set_internal_name('lt_comparable_type')

_int_add_type = py_function_type[TypeSequence([object_type]), _x]

int_type = ObjectType(
    _x,
    {
        '__add__': _int_add_type,
        '__invert__': py_function_type[TypeSequence([]), _x],
        '__sub__': _int_add_type,
        '__invert__': py_function_type[TypeSequence([]), _x],
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

iterator_type = ObjectType(
    _x,
    {
        '__iter__': py_function_type[TypeSequence([]), _x],
        '__next__': py_function_type[TypeSequence([none_type,]), _result_type],
    },
    [_result_type],
)
iterator_type.set_internal_name('iterator_type')

iterable_type = ObjectType(
    _x,
    {
        '__iter__': py_function_type[
            TypeSequence([]), iterator_type[_result_type,]
        ]
    },
    [_result_type],
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

optional_type = _OptionalType()
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
    _x,
    {
        'seek': py_function_type[TypeSequence([int_type]), int_type],
        'read': py_function_type,
        '__enter__': py_function_type,
        '__exit__': py_function_type,
    },
    [],
    # context_manager_type is a structural supertype
    [iterable_type],
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

_element_type_var = IndividualVariable()
_list_getitem_type = py_function_type[
    TypeSequence([int_type]), _element_type_var
].with_overload((slice_type[(optional_type[int_type,],) * 3],), _x)
list_type = ObjectType(
    _x,
    {
        '__getitem__': _list_getitem_type,
        '__iter__': py_function_type[
            TypeSequence([]), iterator_type[_element_type_var,]
        ],
    },
    [_element_type_var],
    nominal=True,
)
list_type.set_internal_name('list_type')

_str_getitem_type = py_function_type[
    TypeSequence([int_type]), _x
].with_overload(
    [
        slice_type[
            optional_type[int_type,],
            optional_type[int_type,],
            optional_type[int_type,],
        ]
    ],
    _x,
)
str_type = ObjectType(
    _x,
    {
        '__getitem__': _str_getitem_type,
        '__add__': py_function_type[TypeSequence([object_type]), _x],
        # FIXME: str doesn't have an __radd__. I added it only to help with
        # type checking.
        '__radd__': py_function_type[TypeSequence([object_type]), _x],
        'find': py_function_type[
            TypeSequence(
                [_x, optional_type[int_type,], optional_type[int_type,]]
            ),
            int_type,
        ],
        'join': py_function_type[TypeSequence([_x, iterable_type[_x,]]), _x],
        '__iter__': py_function_type[TypeSequence([]), iterator_type[_x,]],
        'index': py_function_type[
            TypeSequence(
                [_x, optional_type[int_type,], optional_type[int_type,]]
            ),
            int_type,
        ],
    },
    nominal=True,
)
str_type.set_internal_name('str_type')

ellipsis_type = ObjectType(_x, {})
not_implemented_type = ObjectType(_x, {})

_element_types_var = SequenceVariable()
tuple_type = ObjectType(
    _x,
    {'__getitem__': py_function_type},
    [_element_types_var],
    nominal=True
    # iterable_type is a structural supertype
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
