import concat.level1.typecheck
from concat.level1.typecheck import (
    AttributeError,
    StackMismatchError,
    TypeError,
)
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
    # TODO: Fully replace with <=.
    def is_subtype_of(self, supertype: 'Type') -> bool:
        if supertype == self or supertype == object_type:
            return True
        if isinstance(supertype, IndividualVariable):
            return self.is_subtype_of(supertype.bound)
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

    @abc.abstractproperty
    def attributes(self) -> Mapping[str, 'Type']:
        pass

    @abc.abstractmethod
    def free_type_variables(self) -> Set['_Variable']:
        pass

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
    def to_for_all(self) -> Type:
        return ForAll([], self)

    def __and__(self, other: object) -> 'IndividualType':
        raise NotImplementedError('take advantage of constraints instead')

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

    def apply_substitution(
        self, sub: 'concat.level1.typecheck.Substitutions'
    ) -> Union[IndividualType, '_Variable', List['StackItemType']]:
        if self in sub:
            return sub[self]  # type: ignore
        return self

    def free_type_variables(self) -> Set['_Variable']:
        return {self}


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

    @property
    def attributes(self) -> Mapping[str, 'IndividualType']:
        # FIXME: Constraints?
        return cast(Mapping[str, IndividualType], self.bound.attributes)

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
                elif (
                    self._rest
                    and self._rest not in supertype.free_type_variables()
                ):
                    self._rest.constrain(supertype, constraints)
                elif self._is_empty() and not supertype._is_empty():
                    raise StackMismatchError(self, supertype)
                else:
                    # case where self._rest is in supertype: self._rest cannot
                    # equal supertype because that would produce an infinite
                    # sequence type
                    raise StackMismatchError(self, supertype)
            elif (
                not supertype._individual_types
                and supertype._rest
                and supertype._rest not in self.free_type_variables()
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
                try:
                    self[:-1].constrain(
                        supertype[:-1], constraints, polymorphic
                    )
                except StackMismatchError:
                    raise StackMismatchError(self, supertype)
            else:
                raise StackMismatchError(self, supertype)
        else:
            raise TypeError(
                '{} must be a sequence type, not {}'.format(self, supertype)
            )

    def free_type_variables(self) -> Set['_Variable']:
        ftv: Set[_Variable] = set()
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

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, TypeSequence):
            return super().__eq__(other)
        return self.as_sequence() == other.as_sequence()

    def __hash__(self) -> int:
        return hash(tuple(self.as_sequence()))


# TODO: Actually get rid of ForAll uses. This is a temporary measure since I
# don't want to do that work right now.
def ForAll(type_parameters: Sequence['_Variable'], type: Type) -> Type:
    return ObjectType(IndividualVariable(), type.attributes, type_parameters,)


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

    def generalized_wrt(self, gamma: Dict[str, Type]) -> Type:
        return ObjectType(
            IndividualVariable(),
            {'__call__': self,},
            list(
                self.free_type_variables()
                - _free_type_variables_of_mapping(gamma)
            ),
        )

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

    def free_type_variables(self) -> Set['_Variable']:
        return (
            self.input.free_type_variables()
            | self.output.free_type_variables()
        )

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

    @property
    def attributes(self) -> Mapping[str, 'StackEffect']:
        return {'__call__': self}

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
    raise NotImplementedError('stop using _IntersectionType')


# FIXME: This should be a method on types
def inst(sigma: _Function) -> IndividualType:
    """This is based on the inst function described by Kleffner."""
    if isinstance(sigma, _Function):
        input = [
            inst(type) if isinstance(type, _Function) else type
            for type in sigma.input
        ]
        output = [
            inst(type) if isinstance(type, _Function) else type
            for type in sigma.output
        ]
        return _Function(input, output)
    raise builtins.TypeError(type(sigma))


StackItemType = Union[SequenceVariable, IndividualType]


def _free_type_variables_of_mapping(
    attributes: Mapping[str, Type]
) -> Set[_Variable]:
    ftv: Set[_Variable] = set()
    for sigma in attributes.values():
        ftv |= sigma.free_type_variables()
    return ftv


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
        self,
        sub: 'concat.level1.typecheck.Substitutions',
        _should_quantify_over_type_parameters=True,
    ) -> 'ObjectType':
        from concat.level1.typecheck import Substitutions

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

    # TODO: Remove is_subtype_of and replace uses with constraints
    def is_subtype_of(self, supertype: 'Type') -> bool:
        if supertype in self._nominal_supertypes or supertype == object_type:
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
        elif isinstance(supertype, StackEffect):
            if self._arity != 0:
                raise TypeError(
                    'type constructor {} expected at least one argument cannot be a stack effect (expected effect {})'.format(
                        self, supertype
                    )
                )
            self.get_type_of_attribute('__call__').constrain(
                supertype, constraints
            )
            return
        elif not isinstance(supertype, ObjectType):
            raise NotImplementedError(supertype)
        if self._arity != supertype._arity:
            raise TypeError(
                '{} and {} do not have the same arity'.format(self, supertype)
            )
        # every object type is a subtype of object_type
        if supertype == object_type:
            return
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

    def free_type_variables(self) -> Set[_Variable]:
        ftv = _free_type_variables_of_mapping(self.attributes)
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

    # QUESTION: Define in terms of <= (a <= b and b <= a)? For all kinds of types?
    def __eq__(self, other: object) -> bool:
        from concat.level1.typecheck import Substitutions

        if not isinstance(other, ObjectType):
            return super().__eq__(other)

        if self._nominal or other._nominal:
            return self is other

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

    def _add_overload(
        self, input: Sequence[StackItemType], output: IndividualType
    ) -> None:
        self._overloads.append((input, output))

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

bool_type = ObjectType(_x, {}, nominal=True)
bool_type.set_internal_name('bool_type')

_int_add_type = py_function_type[TypeSequence([object_type]), _x]

int_type = ObjectType(
    _x,
    {
        '__add__': _int_add_type,
        '__invert__': py_function_type[TypeSequence([]), _x],
        '__sub__': _int_add_type,
        '__invert__': py_function_type[TypeSequence([]), _x],
        '__le__': py_function_type[TypeSequence([_x]), bool_type],
    },
    nominal=True,
)
int_type.set_internal_name('int_type')

# FIXME: Use an iterator interface instead of _x
_result_type = IndividualVariable()
iterable_type = ObjectType(
    _x, {'__iter__': py_function_type[TypeSequence([]), _x]}, [_result_type]
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
optional_type = _OptionalType()
context_manager_type.set_internal_name('context_manager_type')

optional_type = _OptionalType()
optional_type.set_internal_name('optional_type')

none_type = ObjectType(_x, {})
none_type.set_internal_name('none_type')

dict_type = ObjectType(
    _x, {'__iter__': py_function_type[TypeSequence([]), object_type]}
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
        # FIXME: __iter__ should return an iterator.
        '__iter__': py_function_type[TypeSequence([]), object_type],
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
        'find': py_function_type[
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

tuple_type = ObjectType(
    _x,
    {'__getitem__': py_function_type}
    # iterable_type is a structural supertype
)
tuple_type.set_internal_name('tuple_type')

base_exception_type = ObjectType(_x, {})
module_type = ObjectType(_x, {})
