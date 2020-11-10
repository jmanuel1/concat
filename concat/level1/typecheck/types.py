import concat.level1.typecheck
from typing import Tuple, Optional, Dict, Sequence, Union, List, Iterator, Set, cast
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
        if supertype is self or supertype is PrimitiveTypes.object:
            return True
        if isinstance(supertype, IndividualVariable):
            return self.is_subtype_of(supertype.bound)
        if isinstance(supertype, TypeWithAttribute):
            try:
                attr_type = self.get_type_of_attribute(supertype.attribute)
            except concat.level1.typecheck.AttributeError:
                return False
            return inst(attr_type.to_for_all()).is_subtype_of(
                inst(supertype.attribute_type.to_for_all())
            )
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

    @abc.abstractmethod
    def apply_substitution(self, _: 'concat.level1.typecheck.Substitutions') -> Union['Type', Sequence['StackItemType']]:
        pass


class IndividualType(Type, abc.ABC):
    @abc.abstractmethod
    def __init__(self) -> None:
        super().__init__()

    def to_for_all(self) -> 'ForAll':
        return ForAll([], self)

    def __and__(self, other: object) -> 'IndividualType':
        if not isinstance(other, IndividualType):
            return NotImplemented
        elif self is PrimitiveTypes.object:
            return other
        elif other is PrimitiveTypes.object:
            return self
        return _IntersectionType(self, other)

    def is_subtype_of(self, supertype: Type) -> bool:
        if (
            isinstance(supertype, PrimitiveType)
            and supertype.parent is PrimitiveTypes.optional
        ):
            if (
                self is PrimitiveTypes.none
                or not supertype.type_arguments
                or self.is_subtype_of(supertype.type_arguments[0])
            ):
                return True
            return False
        return super().is_subtype_of(supertype)

    @abc.abstractmethod
    def collapse_bounds(self) -> 'IndividualType':
        pass


class PrimitiveType(IndividualType):
    def __init__(
        self,
        name: str = '<primitive_type>',
        supertypes: Tuple[IndividualType, ...] = (),
        attributes: Optional[Dict[str, 'IndividualType']] = None,
        type_parameters: Sequence['IndividualVariable'] = (),
    ) -> None:
        self._name = name
        self._supertypes = supertypes
        self._attributes = {} if attributes is None else attributes
        self._type_parameters = type_parameters
        self._type_arguments: Optional[Sequence[IndividualType]] = None
        self._parent: Optional[PrimitiveType] = None
        self._type_argument_cache: Dict[
            Sequence[IndividualType], PrimitiveType
        ] = {}

    def is_subtype_of(self, supertype: Type) -> bool:
        return super().is_subtype_of(supertype) or any(
            map(lambda t: t.is_subtype_of(supertype), self._supertypes)
        )

    def add_supertype(self, supertype: Type) -> None:
        self._supertypes += (supertype,)

    def __getitem__(
        self, types: Union[IndividualType, Sequence[IndividualType]]
    ) -> 'PrimitiveType':
        from concat.level1.typecheck import Substitutions

        if not isinstance(types, collections.abc.Sequence):
            types = (types,)
        if len(types) != len(self._type_parameters):
            raise concat.level1.typecheck.TypeError(
                'type argument mismatch: {} takes {} type arguments, given {}'.format(
                    self, len(self._type_parameters), len(types)
                )
            )
        if types in self._type_argument_cache:
            return self._type_argument_cache[types]
        sub = Substitutions(zip(self._type_parameters, types))
        new_type = sub(self)
        new_type._name = self._name
        new_type._type_arguments = types
        new_type._type_argument_cache = self._type_argument_cache
        new_type._parent = self
        self._type_argument_cache[types] = new_type
        return new_type

    def __repr__(self) -> str:
        return '<primitive type "{}">'.format(self._name)

    def __str__(self) -> str:
        type_arguments_str = ''
        if self._type_arguments is not None:
            type_arguments_str = '[{}]'.format(
                ', '.join(str(arg) for arg in self._type_arguments)
            )
        return self._name + type_arguments_str

    def add_attribute(self, attribute: str, type: 'IndividualType') -> None:
        self._attributes[attribute] = type

    def get_type_of_attribute(self, attribute: str) -> 'IndividualType':
        try:
            return self._attributes[attribute]
        except KeyError:
            raise concat.level1.typecheck.AttributeError(self, attribute)

    def apply_substitution(self, sub: 'concat.level1.typecheck.Substitutions') -> 'PrimitiveType':
        new_attributes = {
            name: sub(type) for name, type in self._attributes.items()
        }
        new_supertypes = tuple(sub(type) for type in self._supertypes)
        if (
            new_attributes == self._attributes
            and new_supertypes == self._supertypes
        ):
            return self
        new_name = '{}[sub {}]'.format(self._name, id(sub))
        return PrimitiveType(new_name, new_supertypes, new_attributes)

    def collapse_bounds(self) -> 'PrimitiveType':
        new_attributes = {
            name: type.collapse_bounds() for name, type in self._attributes.items()
        }
        new_supertypes = tuple(type.collapse_bounds() for type in self._supertypes)
        if (
            new_attributes == self._attributes
            and new_supertypes == self._supertypes
        ):
            return self
        return PrimitiveType(self.name, new_supertypes, new_attributes)

    @property
    def supertypes(self) -> Sequence[Type]:
        return self._supertypes

    @property
    def parent(self) -> 'PrimitiveType':
        return self._parent

    @property
    def type_arguments(self) -> Optional[Sequence[IndividualType]]:
        return self._type_arguments


class _NoReturnType(PrimitiveType):
    def __init__(self) -> None:
        super().__init__('NoReturn')

    def is_subtype_of(self, _: Type) -> Literal[True]:
        return True


class PrimitiveTypes:
    int = PrimitiveType('int')
    bool = PrimitiveType('bool')
    object = PrimitiveType('object')
    context_manager = PrimitiveType('context_manager')
    dict = PrimitiveType('dict')
    module = PrimitiveType('module')
    list: PrimitiveType
    str = PrimitiveType('str')
    py_function: PrimitiveType
    none = PrimitiveType('None')
    optional: PrimitiveType


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
        self.bound = bound or PrimitiveTypes.object

    def is_subtype_of(self, supertype: Type):
        return super().is_subtype_of(supertype) or self.bound.is_subtype_of(
            supertype
        )

    def __hash__(self) -> int:
        return hash((id(self), self.bound))

    def __str__(self) -> str:
        bound = ''
        if self.bound is not PrimitiveTypes.object:
            bound = ' (bound: {})'.format(self.bound)
        return '`t_{}'.format(id(self)) + bound

    def get_type_of_attribute(self, name: str) -> 'IndividualType':
        return self.bound.get_type_of_attribute(name)

    def apply_substitution(self, sub: 'concat.level1.typecheck.Substitutions') -> IndividualType:
        if super().apply_substitution(sub) is not self:
            return cast(IndividualType, super().apply_substitution(sub))
        # If our bound won't change, return the same variable. Without
        # handling this case, parts of unify_ind don't work since it starts
        # returning substitutions from type variables it wasn't originally
        # given.
        bound: IndividualType = sub(self.bound)
        if bound == self.bound:
            return self
        # NOTE: This returns a new, distinct type variable!
        return IndividualVariable(bound)

    def collapse_bounds(self) -> IndividualType:
        return self.bound.collapse_bounds()


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
        return {self.type_1, self.type_2} == {other.type_1, other.type_2}

    def __hash__(self) -> int:
        return hash((self.type_1, self.type_2))

    def apply_substitution(self, sub: 'concat.level1.typecheck.Substitutions') -> 'IndividualType':
        return sub(self.type_1) & sub(self.type_2)

    def collapse_bounds(self) -> 'IndividualType':
        return self.type_1.collapse_bounds() & self.type_2.collapse_bounds()


class PrimitiveInterface(IndividualType):
    def __init__(
        self,
        name: str = '<primitive_interface>',
        attributes: Optional[Dict[str, 'IndividualType']] = None,
    ) -> None:
        self._name = name
        self._attributes = {} if attributes is None else attributes
        self._type_arguments: Optional[Sequence[IndividualType]] = None
        self._type_argument_cache: Dict[
            Sequence[IndividualType], 'PrimitiveInterface'
        ] = {}
        self._parent: Optional[PrimitiveInterface] = None

    def __str__(self) -> str:
        type_arguments_str = ''
        if self._type_arguments is not None:
            joined_argument_strs = ', '.join(map(str, self._type_arguments))
            type_arguments_str = '[' + joined_argument_strs + ']'
        return 'interface {}{}'.format(self._name, type_arguments_str)

    def __getitem__(
        self, types: Union[IndividualType, Sequence[IndividualType]]
    ) -> 'PrimitiveInterface':
        if not isinstance(types, collections.abc.Sequence):
            types = (types,)
        if types in self._type_argument_cache:
            return self._type_argument_cache[types]
        new_interface = PrimitiveInterface(self._name, self._attributes)
        new_interface._type_arguments = types
        new_interface._type_argument_cache = self._type_argument_cache
        new_interface._parent = self
        self._type_argument_cache[types] = new_interface
        return new_interface

    def get_type_of_attribute(self, attribute: str) -> 'IndividualType':
        try:
            return self._attributes[attribute]
        except KeyError:
            raise concat.level1.typecheck.AttributeError(self, attribute)

    def add_attribute(self, attribute: str, type: 'IndividualType') -> None:
        self._attributes[attribute] = type

    def apply_substitution(self, sub: 'concat.level1.typecheck.Substitutions') -> 'PrimitiveInterface':
        new_attributes = {
            name: sub(type) for name, type in self._attributes.items()
        }
        if new_attributes == self._attributes:
            return self
        new_name = '{}[sub {}]'.format(self._name, id(sub))
        new_type_arguments = None
        if self._type_arguments is not None:
            new_type_arguments = cast(Sequence[IndividualType], sub(self._type_arguments))
        new_interface = PrimitiveInterface(new_name, new_attributes)
        new_interface._type_arguments = new_type_arguments
        return new_interface

    def collapse_bounds(self) -> 'PrimitiveInterface':
        new_attributes = {
            name: type.collapse_bounds() for name, type in self._attributes.items()
        }
        if new_attributes == self._attributes:
            return self
        new_interface = PrimitiveInterface(self.name, new_attributes)
        new_interface._type_arguments = self._type_arguments
        return new_interface

    @property
    def attributes(self) -> Dict[str, Type]:
        return self._attributes

    @property
    def name(self) -> str:
        return self._name

    def is_subtype_of(self, supertype: Type) -> bool:
        if super().is_subtype_of(supertype):
            return True
        if isinstance(supertype, PrimitiveInterface):
            if not self.is_related_to(supertype):
                return False
            if supertype._type_arguments is None:
                return True
            if self._type_arguments is None:
                return False
            # since the type arguments are just sequences of individual types,
            # we can use the unifier
            try:
                concat.level1.typecheck.unify([*self._type_arguments], [*supertype._type_arguments])
            except concat.level1.typecheck.TypeError:
                return False
            return True
        return False

    def is_related_to(self, other: 'PrimitiveInterface') -> bool:
        return self._get_earliest_ancestor() is other._get_earliest_ancestor()

    def _get_earliest_ancestor(self) -> 'PrimitiveInterface':
        if self._parent is None:
            return self
        return self._parent._get_earliest_ancestor()

    @property
    def type_arguments(self) -> Sequence[IndividualType]:
        return self._type_arguments


class SequenceVariable(_Variable):
    def __init__(self) -> None:
        super().__init__()

    def __str__(self) -> str:
        return '*t_{}'.format(id(self))


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
                'type argument mismatch in forall type: arguments are {!r}, quantified variables are {!r}'.format(
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
                    'type argument mismatch in forall type: expected individual type for {!r}, got {!r}'.format(
                        variable, argument
                    )
                )
            if isinstance(variable, SequenceVariable) and not isinstance(
                argument, (SequenceVariable, collections.abc.Sequence)
            ):
                raise concat.level1.typecheck.TypeError(
                    'type argument mismatch in forall type: expected sequence type for {!r}, got {!r}'.format(
                        variable, argument
                    )
                )
            sub[variable] = argument
        return sub(self.type)

    def __str__(self) -> str:
        string = 'for all '
        string += ' '.join(map(str, self.quantified_variables))
        string += '. {}'.format(self.type)
        return string

    def __and__(self, other: object) -> 'ForAll':
        if not isinstance(other, ForAll):
            return NotImplemented
        # TODO: Make variables unique
        # FIXME: This could inadvertently capture free variables in either operand
        return ForAll(
            self.quantified_variables + other.quantified_variables,
            self.type & other.type,
        )

    def apply_substitution(self, sub: 'concat.level1.typecheck.Substitutions') -> 'ForAll':
        return ForAll(
            self.quantified_variables,
            concat.level1.typecheck.Substitutions(
                {
                    a: i
                    for a, i in sub.items()
                    if a not in self.quantified_variables
                }
            )(self.type),
        )


class _Function(IndividualType):
    def __init__(
        self,
        input: Sequence['StackItemType'],
        output: Sequence['StackItemType'],
    ) -> None:
        super().__init__()
        self.input = (*input,)
        self.output = (*output,)

    def __iter__(self) -> Iterator[Sequence['StackItemType']]:
        return iter((self.input, self.output))

    def generalized_wrt(self, gamma: Dict[str, Type]) -> ForAll:
        return ForAll(list(_ftv(self) - _ftv(gamma)), self)

    def can_be_complete_program(self) -> bool:
        """Returns true iff the function type unifies with ( -- *out)."""
        out_var = SequenceVariable()
        try:
            concat.level1.typecheck.unify_ind(self, _Function([], [out_var]))
        except concat.level1.typecheck.TypeError:
            return False
        return True

    def compose(self, other: '_Function') -> '_Function':
        """Returns the type of applying self then other to a stack."""
        i2, o2 = other
        (i1, o1) = self
        phi = concat.level1.typecheck.unify(list(o1), list(i2))
        return phi(_Function(i1, o2))

    def __eq__(self, other: object) -> bool:
        """Compares function types for equality up to renaming of variables."""
        if not isinstance(other, _Function):
            return NotImplemented
        input_arity_matches = len(self.input) == len(other.input)
        output_arity_matches = len(self.output) == len(other.output)
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
        self, supertype: Type, _sub: Optional['concat.level1.typecheck.Substitutions'] = None
    ) -> bool:
        if super().is_subtype_of(supertype):
            return True
        if isinstance(supertype, _Function):
            if len(self.input) != len(supertype.input) or len(
                self.output
            ) != len(supertype.output):
                return False
            # Sequence variables are handled through renaming.
            if _sub is None:
                _sub = concat.level1.typecheck.Substitutions()
            input_rename_result = self._rename_sequence_variable(
                self.input, supertype.input, _sub
            )
            output_rename_result = self._rename_sequence_variable(
                supertype.output, self.output, _sub
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
                    _sub(type_from_self),
                    _sub(type_from_supertype),
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
                    _sub(type_from_self),
                    _sub(type_from_supertype),
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
        return '_Function({!r}, {!r})'.format(self.input, self.output)

    def __str__(self) -> str:
        in_types = ' '.join(map(str, self.input))
        out_types = ' '.join(map(str, self.output))
        return '({} -- {})'.format(in_types, out_types)

    def __and__(self, other: object) -> IndividualType:
        if isinstance(other, _Function):
            input = _intersect_sequences(self.input, other.input)
            output = _intersect_sequences(self.output, other.output)
            return _Function(input, output)
        return super().__and__(other)

    def get_type_of_attribute(self, name: str) -> '_Function':
        if name == '__call__':
            return self
        raise concat.level1.typecheck.AttributeError(self, name)

    def apply_substitution(self, sub: 'concat.level1.typecheck.Substitutions') -> '_Function':
        return _Function(sub(self.input), sub(self.output))

    def collapse_bounds(self) -> '_Function':
        counts: Dict[StackItemType, int] = {}
        for type in self.input + self.output:
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


class TypeWithAttribute(IndividualType):
    def __init__(
        self, attribute: str, attribute_type: 'IndividualType'
    ) -> None:
        super().__init__()
        self.attribute = attribute
        self.attribute_type = attribute_type

    def __repr__(self) -> str:
        return 'TypeWithAttribute({!r}, {!r})'.format(self.attribute, self.attribute_type)

    def __str__(self) -> str:
        type = ''
        if self.attribute_type is not PrimitiveTypes.object:
            type = ':' + str(self.attribute_type)
        return '.{}'.format(self.attribute) + type

    def __eq__(self, other: object) -> bool:
        if isinstance(other, TypeWithAttribute):
            return (self.attribute, self.attribute_type) == (other.attribute, other.attribute_type)
        return super().__eq__(other)

    def __hash__(self) -> int:
        return hash((self.attribute, self.attribute_type))

    def get_type_of_attribute(self, name: str) -> 'IndividualType':
        if name != self.attribute:
            raise concat.level1.typecheck.AttributeError(self, name)
        return self.attribute_type

    def apply_substitution(self, sub: 'concat.level1.typecheck.Substitutions') -> 'TypeWithAttribute':
        return TypeWithAttribute(self.attribute, sub(self.attribute_type))

    def collapse_bounds(self) -> 'TypeWithAttribute':
        return TypeWithAttribute(self.attribute, self.attribute_type.collapse_bounds())


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
def inst(
    sigma: Union[ForAll, PrimitiveInterface, _Function]
) -> IndividualType:
    """This is based on the inst function described by Kleffner."""
    if isinstance(sigma, ForAll):
        subs = concat.level1.typecheck.Substitutions(
            {a: type(a)() for a in sigma.quantified_variables}
        )
        return subs(sigma.type)
    if isinstance(sigma, PrimitiveInterface):
        attributes = {}
        for name in sigma.attributes:
            if isinstance(
                sigma.attributes[name], (ForAll, PrimitiveInterface, _Function)
            ):
                attributes[name] = inst(sigma.attributes[name])
            else:
                attributes[name] = sigma.attributes[name]
        return PrimitiveInterface(sigma.name + '[inst]', attributes)
    if isinstance(sigma, _Function):
        input = [
            inst(type)
            if isinstance(type, (ForAll, PrimitiveInterface, _Function))
            else type
            for type in sigma.input
        ]
        output = [
            inst(type)
            if isinstance(type, (ForAll, PrimitiveInterface, _Function))
            else type
            for type in sigma.output
        ]
        return _Function(input, output)
    raise builtins.TypeError(type(sigma))


StackItemType = Union[SequenceVariable, IndividualType]


# FIXME: This should be a method on types.
def _ftv(
    f: Union[Type, Sequence[StackItemType], Dict[str, Type]]
) -> Set[_Variable]:
    """The ftv function described by Kleffner."""
    ftv: Set[_Variable]
    if isinstance(f, (PrimitiveType, PrimitiveInterface)):
        return set()
    elif isinstance(f, _Variable):
        return {f}
    elif isinstance(f, _Function):
        return _ftv(list(f.input)) | _ftv(list(f.output))
    elif isinstance(f, collections.abc.Sequence):
        ftv = set()
        for t in f:
            ftv |= _ftv(t)
        return ftv
    elif isinstance(f, ForAll):
        return _ftv(f.type) - set(f.quantified_variables)
    elif isinstance(f, dict):
        ftv = set()
        for sigma in f.values():
            ftv |= _ftv(sigma)
        return ftv
    elif isinstance(f, _IntersectionType):
        return _ftv(f.type_1) | _ftv(f.type_2)
    elif isinstance(f, TypeWithAttribute):
        return _ftv(f.attribute_type)
    else:
        raise builtins.TypeError(f)


def init_primitives():
    PrimitiveTypes.str.add_attribute(
        '__getitem__',
        PrimitiveTypes.py_function[PrimitiveTypes.int, PrimitiveTypes.str],
    )

    PrimitiveTypes.file = PrimitiveType(
        'file',
        (),
        {'seek': PrimitiveTypes.py_function, 'read': PrimitiveTypes.py_function},
    )

    _element_type_var = IndividualVariable()
    PrimitiveTypes.list = PrimitiveType(
        'list',
        (),
        {
            '__getitem__': PrimitiveTypes.py_function[
                PrimitiveTypes.int, _element_type_var
            ]
        },
        [_element_type_var],
    )

    _of_type_var = IndividualVariable()
    PrimitiveTypes.optional = PrimitiveType(
        'Optional', type_parameters=[_of_type_var]
    )

    PrimitiveInterfaces.invertible.add_attribute('__invert__', PrimitiveTypes.py_function)

    for type in {
        PrimitiveTypes.int,
        PrimitiveTypes.dict,
        PrimitiveTypes.list,
        PrimitiveTypes.file,
    }:
        type.add_supertype(PrimitiveInterfaces.iterable)


class PrimitiveInterfaces:
    invertible = PrimitiveInterface('invertible')
    iterable = PrimitiveInterface('iterable')


# expose _Function as StackEffect
StackEffect = _Function

int_type = PrimitiveTypes.int
float_type = PrimitiveType('float')
no_return_type = _NoReturnType()
object_type = PrimitiveTypes.object

_arg_type_var = IndividualVariable()
_return_type_var = IndividualVariable()
PrimitiveTypes.py_function = PrimitiveType(
    'py_function', (), {}, [_arg_type_var, _return_type_var]
)
py_function_type = PrimitiveTypes.py_function
