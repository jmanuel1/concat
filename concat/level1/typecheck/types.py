import concat.level1.typecheck
from concat.level1.typecheck import AttributeError, TypeError
from concat.level1.typecheck.constraints import Constraints
from typing import (
    Optional,
    Dict,
    Iterable,
    Iterator,
    Sequence,
    Tuple,
    Union,
    List,
    Iterator,
    Set,
    Mapping,
    NoReturn,
    cast,
    overload,
)
from typing_extensions import Literal
import abc
import collections.abc
import builtins


class Type(abc.ABC):
    @abc.abstractmethod
    def __init__(self):
        pass

    # TODO: Fully replace with <=.
    def is_subtype_of(self, supertype: 'Type') -> bool:
        if supertype == self or supertype == object_type:
            return True
        if isinstance(supertype, IndividualVariable):
            return self.is_subtype_of(supertype.bound)
        if isinstance(supertype, _IntersectionType):
            return self.is_subtype_of(supertype.type_1) and self.is_subtype_of(
                supertype.type_2
            )
        return False

    def __le__(self, other: object) -> bool:
        if not isinstance(other, Type):
            return NotImplemented
        return self.is_subtype_of(other)

    def get_type_of_attribute(self, name: str) -> 'IndividualType':
        raise concat.level1.typecheck.AttributeError(self, name)

    def has_attribute(self, name: str) -> bool:
        try:
            self.get_type_of_attribute(name)
            return True
        except concat.level1.typecheck.AttributeError:
            return False

    @abc.abstractmethod
    def apply_substitution(
        self, _: 'concat.level1.typecheck.Substitutions'
    ) -> Union['Type', Sequence['StackItemType']]:
        pass

    @abc.abstractmethod
    def constrain(self, supertype: 'Type', constraints: 'Constraints') -> None:
        pass

    def instantiate(self) -> 'Type':
        return self


class IndividualType(Type, abc.ABC):
    @abc.abstractmethod
    def __init__(self) -> None:
        super().__init__()

    def to_for_all(self) -> 'ForAll':
        return ForAll([], self)

    def __and__(self, other: object) -> 'IndividualType':
        if not isinstance(other, IndividualType):
            return NotImplemented
        elif self == object_type:
            return other
        elif other is object_type:
            return self
        return _IntersectionType(self, other)

    def is_subtype_of(self, supertype: Type) -> bool:
        if (
            isinstance(supertype, ObjectType)
            and supertype.head == optional_type
        ):
            if (
                self == none_type
                or not supertype.type_arguments
                or isinstance(supertype.type_arguments[0], IndividualType)
                and self.is_subtype_of(supertype.type_arguments[0])
            ):
                return True
            return False
        return super().is_subtype_of(supertype)

    @abc.abstractmethod
    def collapse_bounds(self) -> 'IndividualType':
        pass


class _Variable(Type, abc.ABC):
    """Objects that represent type variables.

    Every type variable object is assumed to be unique. Thus, fresh type
    variables can be made simply by creating new objects. They can also be
    compared by identity."""

    @abc.abstractmethod
    def __init__(self) -> None:
        super().__init__()

    def apply_substitution(
        self, sub: 'concat.level1.typecheck.Substitutions'
    ) -> Union[IndividualType, '_Variable', List['StackItemType']]:
        if self in sub:
            return sub[self]  # type: ignore
        return self


class IndividualVariable(_Variable, IndividualType):
    def __init__(self, bound: Optional[IndividualType] = None) -> None:
        super().__init__()
        self._bound = bound

    @property
    def bound(self) -> 'IndividualType':
        return self._bound or object_type

    @property
    def _never_object_type_bound(self) -> Optional[IndividualType]:
        if self._bound == object_type:
            return None
        return self._bound

    def is_subtype_of(self, supertype: Type):
        return super().is_subtype_of(supertype) or self.bound.is_subtype_of(
            supertype
        )

    def constrain(self, supertype: Type, constraints: Constraints) -> None:
        constraints.add(self, supertype)

    # Default __eq__ and __hash__ (equality by object identity) are used.

    def __str__(self) -> str:
        bound = ''
        if self.bound is not object_type:
            bound = ' (bound: {})'.format(self.bound)
        return '`t_{}'.format(id(self)) + bound

    def __repr__(self) -> str:
        if self.bound == object_type:
            bound = ''
        else:
            bound = ', bound: ' + repr(self.bound)
        return '<individual variable {}{}>'.format(id(self), bound)

    def get_type_of_attribute(
        self, name: str, constraints: Constraints = Constraints()
    ) -> 'IndividualType':
        try:
            return self.bound.get_type_of_attribute(name)
        except AttributeError:
            # FIXME: We assume we will get the type object with the attribute.
            return constraints.get_supertype_of(self).get_type_of_attribute(
                name
            )

    def apply_substitution(
        self, sub: 'concat.level1.typecheck.Substitutions'
    ) -> IndividualType:
        if super().apply_substitution(sub) is not self:
            return cast(IndividualType, super().apply_substitution(sub))
        # If our bound won't change, return the same variable. Without
        # handling this case, other code might not work since it starts
        # returning substitutions from type variables it wasn't originally
        # given.
        # TODO: I should probably just separate bounds from type variables.
        if self._never_object_type_bound is None:
            # This might not be correct, but I need to avoid infinite recursion.
            bound = None
        else:
            bound = cast(IndividualType, sub(self._never_object_type_bound))
        if bound == self._never_object_type_bound:
            return self
        # NOTE: This returns a new, distinct type variable!
        return IndividualVariable(bound)

    def collapse_bounds(self) -> IndividualType:
        return self.bound.collapse_bounds()


# TODO: Reevaluate: do I really need this?
class _IntersectionType(IndividualType):
    def __init__(
        self, type_1: 'IndividualType', type_2: 'IndividualType'
    ) -> None:
        self.type_1 = type_1
        self.type_2 = type_2

    def __repr__(self) -> str:
        return '({!r} & {!r})'.format(self.type_1, self.type_2)

    def __str__(self) -> str:
        return '({} & {})'.format(self.type_1, self.type_2)

    def is_subtype_of(self, other: Type) -> bool:
        return (
            super().is_subtype_of(other)
            or self.type_1.is_subtype_of(other)
            or self.type_2.is_subtype_of(other)
        )

    def constrain(self, supertype: Type, constraints: Constraints) -> None:
        raise NotImplementedError('time to get rid of _IntersectionType?')

    def get_type_of_attribute(self, name: str) -> 'IndividualType':
        try:
            return self.type_1.get_type_of_attribute(name)
        except concat.level1.typecheck.TypeError:
            return self.type_2.get_type_of_attribute(name)

    def __eq__(self, other: object) -> bool:
        simple_self = self.type_1 & self.type_2
        if not isinstance(simple_self, _IntersectionType):
            return simple_self == other
        if not isinstance(other, _IntersectionType):
            return super().__eq__(other)
        result = {self.type_1, self.type_2} == {other.type_1, other.type_2}
        return result

    def __hash__(self) -> int:
        simple_self = self.type_1 & self.type_2
        if not isinstance(simple_self, _IntersectionType):
            return hash(simple_self)
        return hash((self.type_1, self.type_2))

    def apply_substitution(
        self, sub: 'concat.level1.typecheck.Substitutions'
    ) -> 'IndividualType':
        type_1 = cast(IndividualType, sub(self.type_1))
        type_2 = cast(IndividualType, sub(self.type_2))
        return type_1 & type_2

    def collapse_bounds(self) -> 'IndividualType':
        return self.type_1.collapse_bounds() & self.type_2.collapse_bounds()


class SequenceVariable(_Variable):
    def __init__(self) -> None:
        super().__init__()

    def __str__(self) -> str:
        return '*t_{}'.format(id(self))

    def constrain(self, supertype: Type, constraints: Constraints) -> None:
        if not isinstance(supertype, (SequenceVariable, TypeSequence)):
            raise TypeError(
                '{} must be a sequence type, not {}'.format(self, supertype)
            )
        constraints.add(self, supertype)
        constraints.add(supertype, self)

    def get_type_of_attribute(self, name: str) -> NoReturn:
        raise TypeError(
            'the sequence type {} does not hold attributes'.format(self)
        )


class TypeSequence(Type, Iterable['StackItemType']):
    def __init__(self, sequence: Sequence['StackItemType']) -> None:
        self._rest: Optional[SequenceVariable]
        # FIXME: This assertion shoudn't fail, but it does.
        assert not isinstance(sequence, TypeSequence)
        assert all(not isinstance(i, TypeSequence) for i in sequence)
        if sequence and isinstance(sequence[0], SequenceVariable):
            self._rest = sequence[0]
            self._individual_types = sequence[1:]
        else:
            try:
                assert all(
                    not isinstance(i, SequenceVariable) for i in sequence
                )
            except AssertionError:
                raise
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

    def constrain(
        self, supertype: Type, constraints: Constraints, polymorphic=False
    ) -> None:
        """Constrain self to be a subtype of supertype.

        The `polymorphic` flag is used to enable special handling of type
        variables so that type information can be propagated into calls of
        named functions.
        """
        if isinstance(supertype, SequenceVariable):
            supertype.constrain(self, constraints)
        elif isinstance(supertype, TypeSequence):
            if self._is_empty() and supertype._is_empty():
                return
            elif (
                self._is_empty()
                and supertype._rest
                and not supertype._individual_types
            ):
                supertype._rest.constrain(self, constraints)
            elif (
                supertype._is_empty()
                and self._rest
                and not self._individual_types
            ):
                self._rest.constrain(supertype, constraints)
            elif not self._individual_types:
                if (
                    self._rest is supertype._rest
                    and not supertype._individual_types
                ):
                    return
                elif self._rest and self._rest not in _ftv(supertype):
                    self._rest.constrain(supertype, constraints)
                elif self._is_empty() and not supertype._is_empty():
                    raise TypeError(
                        'The stack is empty here, but sequence type {} was expected'.format(
                            supertype
                        )
                    )
                else:
                    # FIXME: handle case where self._rest is in supertype
                    assert False
            elif (
                not supertype._individual_types
                and supertype._rest
                and supertype._rest not in _ftv(self)
            ):
                supertype._rest.constrain(self, constraints)
            elif self._individual_types and supertype._individual_types:
                self._individual_types[-1].constrain(
                    supertype._individual_types[-1], constraints
                )
                # NOTE: Simplifying assumption: If polymorphic is True,
                # constrain individual variables in the second sequence type to
                # be *equal* to the corresponding type in the first sequence
                # type.
                is_variable = isinstance(
                    supertype._individual_types[-1], IndividualVariable
                )
                if polymorphic and is_variable:
                    supertype._individual_types[-1].constrain(
                        self._individual_types[-1], constraints
                    )
                self[:-1].constrain(supertype[:-1], constraints, polymorphic)
            else:
                raise TypeError(
                    ' {} is not a subtype of {}'.format(self, supertype)
                )
        else:
            raise TypeError(
                '{} must be a sequence type, not {}'.format(self, supertype)
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

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, TypeSequence):
            return super().__eq__(other)
        return self.as_sequence() == other.as_sequence()

    def __hash__(self) -> int:
        return hash(tuple(self.as_sequence()))


# FIXME: Subtyping of universal types.
class ForAll(Type):
    def __init__(
        self, quantified_variables: List[_Variable], type: 'IndividualType'
    ) -> None:
        super().__init__()
        self.quantified_variables = quantified_variables
        self.type = type

    def to_for_all(self) -> 'ForAll':
        return self

    def __getitem__(
        self,
        type_arguments: Sequence[
            Union['StackItemType', Sequence['StackItemType']]
        ],
    ) -> IndividualType:
        sub = concat.level1.typecheck.Substitutions()
        if len(type_arguments) != len(self.quantified_variables):
            raise concat.level1.typecheck.TypeError(
                'type argument mismatch in forall type: arguments are {!r}, '
                'quantified variables are {!r}'.format(
                    type_arguments, self.quantified_variables
                )
            )
        for argument, variable in zip(
            type_arguments, self.quantified_variables
        ):
            if isinstance(variable, IndividualVariable) and not isinstance(
                argument, IndividualType
            ):
                raise concat.level1.typecheck.TypeError(
                    'type argument mismatch in forall type: expected '
                    'individual type for {!r}, got {!r}'.format(
                        variable, argument
                    )
                )
            if isinstance(variable, SequenceVariable) and not isinstance(
                argument, (SequenceVariable, collections.abc.Sequence)
            ):
                raise concat.level1.typecheck.TypeError(
                    'type argument mismatch in forall type: expected sequence '
                    'type for {!r}, got {!r}'.format(variable, argument)
                )
            if isinstance(argument, collections.abc.Sequence):
                sub[variable] = [*argument]
            else:
                sub[variable] = argument
        return cast(IndividualType, sub(self.type))

    def __str__(self) -> str:
        string = 'for all '
        string += ' '.join(map(str, self.quantified_variables))
        string += '. {}'.format(self.type)
        return string

    def __and__(self, other: object) -> 'ForAll':
        if not isinstance(other, ForAll):
            return NotImplemented
        # TODO: Make variables unique
        # FIXME: This could inadvertently capture free variables in either
        # operand
        return ForAll(
            self.quantified_variables + other.quantified_variables,
            self.type & other.type,
        )

    def apply_substitution(
        self, sub: 'concat.level1.typecheck.Substitutions'
    ) -> 'ForAll':
        return ForAll(
            self.quantified_variables,
            cast(
                IndividualType,
                concat.level1.typecheck.Substitutions(
                    {
                        a: i
                        for a, i in sub.items()
                        if a not in self.quantified_variables
                    }
                )(self.type),
            ),
        )

    def constrain(self, supertype: Type, constraints: Constraints) -> None:
        raise NotImplementedError('time to get rid of ForAll')

    def instantiate(self) -> 'IndividualType':
        subs = concat.level1.typecheck.Substitutions(
            {a: type(a)() for a in self.quantified_variables}
        )
        return cast(IndividualType, subs(self.type))


# TODO: Rename to StackEffect at all use sites.
class _Function(IndividualType):
    def __init__(
        self,
        input: Iterable['StackItemType'],
        output: Iterable['StackItemType'],
    ) -> None:
        super().__init__()
        self.input = TypeSequence(tuple(input))
        self.output = TypeSequence(tuple(output))

    def __iter__(self) -> Iterator[Sequence['StackItemType']]:
        return iter((tuple(self.input), tuple(self.output)))

    def generalized_wrt(self, gamma: Dict[str, Type]) -> ForAll:
        return ForAll(list(_ftv(self) - _ftv(gamma)), self)

    def can_be_complete_program(self) -> bool:
        """Returns true iff the function type is a subtype of ( -- *out)."""
        from concat.level1.typecheck import _global_constraints

        out_var = SequenceVariable()
        try:
            # FIXME: Use a temporary constraints object.
            _global_constraints.add(self, _Function([], [out_var]))
        except concat.level1.typecheck.TypeError:
            # FIXME: Undo failed constraints.
            return False
        return True

    # TODO: If I don't use this anywhere, I should remove it.
    def compose(self, other: '_Function') -> '_Function':
        """Returns the type of applying self then other to a stack."""
        i2, o2 = other
        (i1, o1) = self
        constraints = Constraints()
        constraints.add(TypeSequence(o1), TypeSequence(i2))
        phi = constraints.equalities_as_substitutions()
        return phi(_Function(i1, o2))

    def __eq__(self, other: object) -> bool:
        """Compares function types for equality up to renaming of variables."""
        if not isinstance(other, _Function):
            return NotImplemented
        input_arity_matches = len(tuple(self.input)) == len(tuple(other.input))
        output_arity_matches = len(tuple(self.output)) == len(
            tuple(other.output)
        )
        arities_match = input_arity_matches and output_arity_matches
        if not arities_match:
            return False
        # We can't use plain unification here because variables can only map to
        # variables of the same type.
        subs = concat.level1.typecheck.Substitutions()
        type_pairs = zip(
            [*self.input, *self.output], [*other.input, *other.output]
        )
        for type1, type2 in type_pairs:
            if isinstance(type1, IndividualVariable) and isinstance(
                type2, IndividualVariable
            ):
                # FIXME: This equality check should include alpha equivalence.
                if type1.bound == type2.bound:
                    subs[type2] = type1
            elif isinstance(type1, SequenceVariable) and isinstance(
                type2, SequenceVariable
            ):
                subs[type2] = type1
            type2 = subs(type2)  # type: ignore
            if type1 != type2:
                return False
        return True

    def __hash__(self) -> int:
        # FIXME: Alpha equivalence
        return hash((self.input, self.output))

    def is_subtype_of(
        self,
        supertype: Type,
        _sub: Optional['concat.level1.typecheck.Substitutions'] = None,
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
                _sub = concat.level1.typecheck.Substitutions()
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

    def constrain(self, supertype: Type, constraints: Constraints) -> None:
        if not supertype.has_attribute('__call__'):
            raise TypeError(
                '{} is not a subtype of {}'.format(self, supertype)
            )
        fun_type = supertype.get_type_of_attribute('__call__')
        if not isinstance(fun_type, _Function):
            raise TypeError(
                '{} is not a subtype of {}'.format(self, supertype)
            )
        constraints.add(self.input, fun_type.input)
        constraints.add(self.output, fun_type.output)

    @staticmethod
    def _rename_sequence_variable(
        supertype_list: Sequence['StackItemType'],
        subtype_list: Sequence['StackItemType'],
        sub: 'concat.level1.typecheck.Substitutions',
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

    def __and__(self, other: object) -> IndividualType:
        if isinstance(other, _Function):
            input = _intersect_sequences(tuple(self.input), tuple(other.input))
            output = _intersect_sequences(
                tuple(self.output), tuple(other.output)
            )
            return _Function(input, output)
        return super().__and__(other)

    def get_type_of_attribute(self, name: str) -> '_Function':
        if name == '__call__':
            return self
        raise concat.level1.typecheck.AttributeError(self, name)

    def apply_substitution(
        self, sub: 'concat.level1.typecheck.Substitutions'
    ) -> '_Function':
        return _Function(sub(self.input), sub(self.output))

    def collapse_bounds(self) -> '_Function':
        counts: Dict[StackItemType, int] = {}
        for type in (*self.input, *self.output):
            counts[type] = counts.get(type, 0) + 1
        collapsed_input, collapsed_output = [], []
        for type in self.input:
            if isinstance(type, SequenceVariable) or counts[type] > 1:
                collapsed_input.append(type)
            else:
                collapsed_input.append(type.collapse_bounds())
        for type in self.output:
            if isinstance(type, SequenceVariable) or counts[type] > 1:
                collapsed_output.append(type)
            else:
                collapsed_output.append(type.collapse_bounds())
        return _Function(collapsed_input, collapsed_output)

    def bind(self) -> '_Function':
        return _Function(self.input[:-1], self.output)


class QuotationType(_Function):
    def __init__(self, fun_type: _Function) -> None:
        super().__init__(fun_type.input, fun_type.output)

    def is_subtype_of(
        self,
        supertype: Type,
        _sub: Optional['concat.level1.typecheck.Substitutions'] = None,
    ) -> bool:
        if super().is_subtype_of(supertype, _sub):
            return True
        if supertype == iterable_type:
            return True
        return False

    def constrain(self, supertype: Type, constraints: Constraints) -> None:
        if (
            isinstance(supertype, ObjectType)
            and supertype.head == iterable_type
        ):
            # FIXME: Don't present new variables every time.
            # FIXME: Account for the types of the elements of the quotation.
            in_var = IndividualVariable()
            out_var = IndividualVariable()
            quotation_iterable_type = iterable_type[
                _Function([in_var], [out_var]),
            ]
            quotation_iterable_type.constrain(supertype, constraints)
            return
        super().constrain(supertype, constraints)

    def apply_substitution(
        self, sub: 'concat.level1.typecheck.Substitutions'
    ) -> 'QuotationType':
        return QuotationType(super().apply_substitution(sub))


def _intersect_sequences(
    seq1: Sequence['StackItemType'], seq2: Sequence['StackItemType']
) -> Sequence['StackItemType']:
    if seq1 and isinstance(seq1[-1], SequenceVariable):
        return seq2
    elif seq2 and isinstance(seq2[-1], SequenceVariable):
        return seq1
    elif not seq1 and not seq2:
        return ()
    elif not seq1 or not seq2:
        return (no_return_type,)
    else:
        return (
            *_intersect_sequences(seq1[:-1], seq2[:-1]),
            cast(IndividualType, seq1[-1]) & cast(IndividualType, seq2[-1]),
        )


# FIXME: This should be a method on types
def inst(sigma: Union[ForAll, _Function]) -> IndividualType:
    """This is based on the inst function described by Kleffner."""
    if isinstance(sigma, ForAll):
        subs = concat.level1.typecheck.Substitutions(
            {a: type(a)() for a in sigma.quantified_variables}
        )
        return cast(IndividualType, subs(sigma.type))
    if isinstance(sigma, _Function):
        input = [
            inst(type) if isinstance(type, (ForAll, _Function)) else type
            for type in sigma.input
        ]
        output = [
            inst(type) if isinstance(type, (ForAll, _Function)) else type
            for type in sigma.output
        ]
        return _Function(input, output)
    if isinstance(sigma, _IntersectionType):
        return inst(sigma.type_1) & inst(sigma.type_2)
    raise builtins.TypeError(type(sigma))


StackItemType = Union[SequenceVariable, IndividualType]


# FIXME: This should be a method on types.
def _ftv(
    f: Union[Type, Sequence[StackItemType], Mapping[str, Type]]
) -> Set[_Variable]:
    """The ftv function described by Kleffner."""
    ftv: Set[_Variable]
    if isinstance(f, _Variable):
        return {f}
    elif isinstance(f, _Function):
        return _ftv(list(f.input)) | _ftv(list(f.output))
    elif isinstance(f, collections.abc.Sequence):
        ftv = set()
        for t in f:
            ftv |= _ftv(t)
        return ftv
    elif isinstance(f, TypeSequence):
        return _ftv(f.as_sequence())
    elif isinstance(f, ForAll):
        return _ftv(f.type) - set(f.quantified_variables)
    elif isinstance(f, dict):
        ftv = set()
        for sigma in f.values():
            ftv |= _ftv(sigma)
        return ftv
    elif isinstance(f, _IntersectionType):
        return _ftv(f.type_1) | _ftv(f.type_2)
    elif isinstance(f, ObjectType):
        ftv = _ftv(f.attributes)
        for arg in f.type_arguments:
            ftv |= _ftv(arg)
        # QUESTION: Include supertypes?
        ftv -= {f.self_type, *f.type_parameters}
        return ftv
    else:
        raise builtins.TypeError(f)


def init_primitives():
    pass


TypeArguments = Sequence[Union[StackItemType, TypeSequence]]


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
        from concat.level1.typecheck import Substitutions

        # make the variable unique
        self._self_type = IndividualVariable()
        self_sub = Substitutions({self_type: self._self_type})

        self._attributes = {
            name: self_sub(t) for name, t in attributes.items()
        }

        self._type_parameters = type_parameters
        self._nominal_supertypes = tuple(
            self_sub(TypeSequence(nominal_supertypes))
        )
        self._nominal = nominal

        type_arguments = [
            cast(Union[StackItemType, TypeSequence], self_sub(arg))
            for arg in _type_arguments
        ]
        self._type_arguments: TypeArguments = type_arguments

        self._head = _head or self

        self._internal_name: Optional[str] = None
        self._internal_name = self._head._internal_name

        self._other_kwargs = _other_kwargs.copy()
        if '_type_arguments' in self._other_kwargs:
            del self._other_kwargs['_type_arguments']
        if 'nominal' in self._other_kwargs:
            del self._other_kwargs['nominal']

    def collapse_bounds(self) -> 'ObjectType':
        return ObjectType(
            self._self_type,
            {
                attr: t.collapse_bounds()
                for attr, t in self._attributes.items()
            },
            type_parameters=self._type_parameters,
            nominal_supertypes=self._nominal_supertypes,
            nominal=self._nominal,
            _type_arguments=self._type_arguments,
            _head=self if self._head is None else self._head,
            **self._other_kwargs,
        )

    def apply_substitution(
        self, sub: 'concat.level1.typecheck.Substitutions'
    ) -> 'ObjectType':
        from concat.level1.typecheck import Substitutions

        sub = Substitutions(
            {
                a: i
                for a, i in sub.items()
                if a not in self._type_parameters and a is not self._self_type
            }
        )
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
        return type(self)(
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

    def is_subtype_of(self, supertype: 'Type') -> bool:
        if supertype in self._nominal_supertypes:
            return True
        if isinstance(supertype, ObjectType) and supertype._nominal:
            return False

        if (
            isinstance(supertype, _Function)
            or isinstance(supertype, ObjectType)
            and supertype._head == py_function_type
        ):
            # TODO: I don't like making this special case. Maybe make
            # py_function_type a special subclass of ObjectType?
            # FIXME: Clean up this logic.
            if self.head == py_function_type and isinstance(
                supertype, ObjectType
            ):
                # TODO: Multiple argument types
                # NOTE: make sure types are of same kind (arity)
                if len(self._type_parameters) != len(
                    supertype._type_parameters
                ):
                    return False
                if len(self._type_parameters) == 0:
                    return True
                elif len(self._type_parameters) == 2:
                    # both are py_function_type
                    return True
                assert isinstance(supertype._type_arguments[0], IndividualType)
                assert isinstance(self._type_arguments[1], IndividualType)
                return (
                    supertype._type_arguments[0] <= self._type_arguments[0]
                    and self._type_arguments[1] <= supertype._type_arguments[1]
                )
            if '__call__' not in self._attributes:
                return False
            return self._attributes['__call__'] <= supertype
        if not isinstance(supertype, ObjectType):
            return super().is_subtype_of(supertype)
        for attr, type in supertype._attributes.items():
            if attr not in self._attributes:
                return False
            sub = concat.level1.typecheck.Substitutions(
                {self._self_type: supertype._self_type}
            )
            if not (cast(IndividualType, sub(self._attributes[attr])) <= type):
                return False
        return True

    def constrain(self, supertype: Type, constraints: Constraints) -> None:
        if isinstance(supertype, IndividualVariable):
            constraints.add(self, supertype)
            return
        elif isinstance(supertype, (SequenceVariable, TypeSequence)):
            raise TypeError(
                '{} is an individual type, but {} is a sequence type'.format(
                    self, supertype
                )
            )
        elif not isinstance(supertype, ObjectType):
            raise NotImplementedError(supertype)
        if self._arity != supertype._arity:
            raise TypeError(
                '{} and {} do not have the same arity'.format(self, supertype)
            )

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
                # don't constrain the type arguments, constrain those based on
                # the attributes

        # constraining to an optional type
        if supertype._head == optional_type and supertype._arity == 0:
            try:
                self.constrain(none_type, constraints)
                return
            except TypeError:
                self.constrain(supertype._type_arguments[0], constraints)
                return

        for name in supertype._attributes:
            type = self.get_type_of_attribute(name)
            type.constrain(supertype.get_type_of_attribute(name), constraints)
        for self_param, super_param in zip(
            self._type_parameters, supertype._type_parameters
        ):
            # FIXME: Contravariance? Invariance?
            constraints.add(self_param, super_param)

    def get_type_of_attribute(self, attribute: str) -> IndividualType:
        if attribute not in self._attributes:
            raise AttributeError(self, attribute)

        self_sub = concat.level1.typecheck.Substitutions(
            {self._self_type: self}
        )

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
        return repr(self)

    def set_internal_name(self, name: str) -> None:
        self._internal_name = name

    # QUESTION: Define in terms of <= (a <= b and b <= a)? For all kinds of types?
    def __eq__(self, other: object) -> bool:
        from concat.level1.typecheck import Substitutions

        if not isinstance(other, ObjectType):
            return super().__eq__(other)
        sub = Substitutions({self._self_type: other._self_type})
        subbed_attributes = {
            attr: sub(t) for attr, t in self._attributes.items()
        }
        if subbed_attributes != other._attributes:
            return False

        if len(self._type_parameters) != len(other._type_parameters) or len(
            self._type_arguments
        ) != len(other._type_arguments):
            return False
        # We can't use plain unification here because variables can only map to
        # variables of the same type.
        subs = Substitutions()
        type_pairs = zip(
            [*self._type_parameters, *self._type_arguments],
            [*other._type_parameters, *other._type_arguments],
        )
        for type1, type2 in type_pairs:
            if isinstance(type1, IndividualVariable) and isinstance(
                type2, IndividualVariable
            ):
                # FIXME: This equality check should include alpha equivalence.
                if type1.bound == type2.bound:
                    subs[type2] = type1
            elif isinstance(type1, SequenceVariable) and isinstance(
                type2, SequenceVariable
            ):
                subs[type2] = type1
            if isinstance(type2, collections.abc.Sequence):
                type2 = tuple(subs(TypeSequence(type2)))
            else:
                type2 = subs(type2)  # type: ignore
            # Make sure that type1 is also a tuple if it's a sequence so that
            # it can be compared with type2
            if isinstance(type1, collections.abc.Sequence):
                type1 = tuple(type1)
            if type1 != type2:
                return False
        if self._nominal != other._nominal:
            return False
        return True

    _hash_variable = None

    def __hash__(self) -> int:
        from concat.level1.typecheck import Substitutions

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
        from concat.level1.typecheck import Substitutions

        sub = Substitutions(zip(self._type_parameters, type_arguments))
        result = sub(self)
        # HACK: We remove the parameters and add arguments through mutation.
        result._type_parameters = ()
        result._type_arguments = type_arguments
        return result

    def instantiate(self) -> 'ObjectType':
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
        return self._attributes['__init__'].bind() <= supertype


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
        # assert self._head == py_function_type
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
        from concat.level1.typecheck import Substitutions

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
        self, sub: 'concat.level1.typecheck.Substitutions'
    ) -> 'PythonFunctionType':
        if self._arity == 0:
            type = py_function_type[
                sub(TypeSequence(self.input)), sub(self.output)
            ]
            for overload in self._overloads:
                type = type.with_overload(
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
        self, input_types: Sequence[StackItemType], constraints: Constraints
    ) -> 'PythonFunctionType':
        # FIXME: use temporary constraints
        for overload in [(self.input, self.output), *self._overloads]:
            for a, b in zip(input_types, overload[0]):
                try:
                    a.constrain(b, constraints)
                except TypeError:
                    break
            else:
                return py_function_type[TypeSequence(overload[0]), overload[1]]
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

    def bind(self) -> 'PythonFunctionType':
        assert self._arity == 0
        inputs = self.input[1:]
        output = self.output
        return self._head[TypeSequence(inputs), output]


class _NoReturnType(ObjectType):
    def __init__(self) -> None:
        x = IndividualVariable()
        super().__init__(x, {})

    def is_subtype_of(self, _: Type) -> Literal[True]:
        return True

    def apply_substitution(
        self, sub: 'concat.level1.typecheck.Substitutions'
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

    # def constrain(self, supertype, )

    def apply_substitution(
        self, sub: 'concat.level1.typecheck.Substitutions'
    ) -> '_OptionalType':
        return _OptionalType(tuple(sub(TypeSequence(self._type_arguments))))


def _iterable_to_str(iterable: Iterable) -> str:
    return '[' + ', '.join(map(str, iterable)) + ']'


# expose _Function as StackEffect
StackEffect = _Function

_x = IndividualVariable()


float_type = ObjectType(_x, {}, nominal=True)
no_return_type = _NoReturnType()
object_type = ObjectType(_x, {})

_arg_type_var = SequenceVariable()
_return_type_var = IndividualVariable()
py_function_type = PythonFunctionType(
    _x, {}, type_parameters=[_arg_type_var, _return_type_var]
)

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

_int_add_type = py_function_type[TypeSequence([object_type]), _x]
# FIXME: subtractable_type are structural supertypes
# but for now they are both explicit
int_type = ObjectType(
    _x,  # FIXME: Make unique for each type.
    {
        '__add__': _int_add_type,
        '__invert__': py_function_type[TypeSequence([]), _x],
    },
    [],
    [subtractable_type],
    nominal=True,
)
int_type.set_internal_name('int_type')

# FIXME: Use an iterator interface instead of _x
_result_type = IndividualVariable()
iterable_type = ObjectType(
    _x, {'__iter__': py_function_type[TypeSequence([]), _x]}, [_result_type]
)

context_manager_type = ObjectType(
    _x,
    {
        # TODO: Add argument and return types. I think I'll need a special
        # py_function representation for that.
        '__enter__': py_function_type,
        '__exit__': py_function_type,
    },
)
optional_type = _OptionalType()

none_type = ObjectType(_x, {})
none_type.set_internal_name('none_type')

dict_type = ObjectType(_x, {}, [], [iterable_type])
bool_type = ObjectType(_x, {})
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
)

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
        # FIXME: __iter__ should return an iterator.
        '__iter__': py_function_type[TypeSequence([]), object_type],
    },
    [_element_type_var],
    nominal=True,
)
list_type.set_internal_name('list_type')

str_type = ObjectType(
    _x, {'__getitem__': py_function_type[TypeSequence([int_type]), _x]}
)

ellipsis_type = ObjectType(_x, {})
not_implemented_type = ObjectType(_x, {})
tuple_type = ObjectType(
    _x,
    {'__getitem__': py_function_type}
    # iterable_type is a structural supertype
)
base_exception_type = ObjectType(_x, {})
module_type = ObjectType(_x, {})
