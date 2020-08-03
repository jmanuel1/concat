"""The Concat type checker.

The type inference algorithm is based on the one described in "Robert Kleffner:
A Foundation for Typed Concatenative Languages, April 2017."
"""

import abc
import dataclasses
import builtins
import collections.abc
from typing import (
    List,
    Set,
    Tuple,
    Dict,
    Iterator,
    Union,
    Optional,
    Callable,
    Sequence,
    NoReturn,
    TYPE_CHECKING,
    overload,
    cast,
)
import concat.level0.parse
import concat.level1.operators
import concat.level1.parse

if TYPE_CHECKING:
    import concat.astutils


class StaticAnalysisError(Exception):
    def __init__(self, message: str) -> None:
        self._message = message
        self.location = None

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
    def __init__(self, name: concat.level0.parse.NameWordNode):
        super().__init__(name)
        self._name = name
        self.location = name.location

    def __str__(self):
        return 'name "{}" not previously defined (error at {}:{})'.format(
            self._name.value, *self.location
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


class Type(abc.ABC):
    @abc.abstractmethod
    def __init__(self):
        pass

    def is_subtype_of(self, supertype: 'Type') -> bool:
        if supertype is self or supertype is PrimitiveTypes.object:
            return True
        if isinstance(supertype, IndividualVariable):
            return self.is_subtype_of(supertype.bound)
        if isinstance(supertype, TypeWithAttribute):
            try:
                attr_type = self.get_type_of_attribute(supertype.attribute)
            except AttributeError:
                return False
            return inst(attr_type.to_for_all()).is_subtype_of(
                inst(supertype.attribute_type.to_for_all())
            )
        if isinstance(supertype, _IntersectionType):
            return self.is_subtype_of(supertype.type_1) and self.is_subtype_of(
                supertype.type_2
            )
        return False

    def get_type_of_attribute(self, name: str) -> 'IndividualType':
        raise AttributeError(self, name)

    @abc.abstractmethod
    def apply_substitution(self, _: 'Substitutions') -> 'Type':
        pass


class IndividualType(Type, abc.ABC):
    @abc.abstractmethod
    def __init__(self) -> None:
        super().__init__()

    def to_for_all(self) -> 'ForAll':
        return ForAll([], self)

    def __and__(self, other: object) -> '_IntersectionType':
        if not isinstance(self, IndividualType) or not isinstance(
            other, IndividualType
        ):
            return NotImplemented
        return _IntersectionType(self, other)


@dataclasses.dataclass
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
        except TypeError:
            return self.type_2.get_type_of_attribute(name)

    def __hash__(self) -> int:
        return hash((self.type_1, self.type_2))

    def apply_substitution(self, sub: 'Substitutions') -> '_IntersectionType':
        return sub(self.type_1) & sub(self.type_2)


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
            raise AttributeError(self, attribute)

    def add_attribute(self, attribute: str, type: 'IndividualType') -> None:
        self._attributes[attribute] = type

    def apply_substitution(self, sub: 'Substitutions') -> 'PrimitiveInterface':
        new_attributes = {
            name: sub(type) for name, type in self._attributes.items()
        }
        if new_attributes == self._attributes:
            return self
        new_name = '{}[sub {}]'.format(self._name, id(sub))
        new_type_arguments = sub(self._type_arguments)
        new_interface = PrimitiveInterface(new_name, new_attributes)
        new_interface._type_arguments = new_type_arguments
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
                unify([*self._type_arguments], [*supertype._type_arguments])
            except TypeError:
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


class PrimitiveType(IndividualType):
    def __init__(
        self,
        name: str = '<primitive_type>',
        supertypes: Tuple[Type, ...] = (),
        attributes: Optional[Dict[str, 'IndividualType']] = None,
    ) -> None:
        self._name = name
        self._supertypes = supertypes
        self._attributes = {} if attributes is None else attributes

    def is_subtype_of(self, supertype: Type) -> bool:
        return super().is_subtype_of(supertype) or any(
            map(lambda t: t.is_subtype_of(supertype), self._supertypes)
        )

    def add_supertype(self, supertype: Type) -> None:
        self._supertypes += (supertype,)

    def __str__(self) -> str:
        return self._name

    def add_attribute(self, attribute: str, type: 'IndividualType') -> None:
        self._attributes[attribute] = type

    def get_type_of_attribute(self, attribute: str) -> 'IndividualType':
        try:
            return self._attributes[attribute]
        except KeyError:
            raise AttributeError(self, attribute)

    def apply_substitution(self, sub: 'Substitutions') -> 'PrimitiveType':
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

    @property
    def supertypes(self) -> Sequence[Type]:
        return self._supertypes


class _Variable(Type, abc.ABC):
    """Objects that represent type variables.

    Every type variable object is assumed to be unique. Thus, fresh type
    variables can be made simply by creating new objects. They can also be
    compared by identity."""

    @abc.abstractmethod
    def __init__(self) -> None:
        super().__init__()

    def apply_substitution(
        self, sub: 'Substitutions'
    ) -> Union[IndividualType, '_Variable', List[Type]]:
        if self in sub:
            return sub[self]  # type: ignore
        return self


class SequenceVariable(_Variable):
    def __init__(self) -> None:
        super().__init__()

    def __str__(self) -> str:
        return '*t_{}'.format(id(self))


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

    def apply_substitution(self, sub: 'Substitutions') -> IndividualType:
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


class ForAll(Type):
    def __init__(
        self, quantified_variables: List[_Variable], type: 'IndividualType'
    ) -> None:
        super().__init__()
        self.quantified_variables = quantified_variables
        self.type = type

    def to_for_all(self) -> 'ForAll':
        return self

    def __str__(self) -> str:
        string = 'for all '
        string += ' '.join(map(str, self.quantified_variables))
        string += '. {}'.format(self.type)
        return string

    def apply_substitution(self, sub: 'Substitutions') -> 'ForAll':
        return ForAll(
            self.quantified_variables,
            Substitutions(
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
        self.input = input
        self.output = output

    def __iter__(self) -> Iterator[Sequence['StackItemType']]:
        return iter((self.input, self.output))

    def generalized_wrt(self, gamma: Dict[str, Type]) -> ForAll:
        return ForAll(list(_ftv(self) - _ftv(gamma)), self)

    def can_be_complete_program(self) -> bool:
        """Returns true iff the function type unifies with ( -- *out)."""
        out_var = SequenceVariable()
        try:
            unify_ind(self, _Function([], [out_var]))
        except TypeError:
            return False
        return True

    def compose(self, other: '_Function') -> '_Function':
        """Returns the type of applying self then other to a stack."""
        i2, o2 = other
        (i1, o1) = self
        phi = unify(list(o1), list(i2))
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
        subs = Substitutions()
        type_pairs = zip(
            [*self.input, *self.output], [*other.input, *other.output]
        )
        for type1, type2 in type_pairs:
            # FIXME: Check bounds of individual type variables
            if isinstance(type1, IndividualVariable) and isinstance(
                type2, IndividualVariable
            ):
                subs[type2] = type1
            elif isinstance(type1, SequenceVariable) and isinstance(
                type2, SequenceVariable
            ):
                subs[type2] = type1
            type2 = subs(type2)  # type: ignore
            if type1 != type2:
                return False
        return True

    def is_subtype_of(
        self, supertype: Type, _sub: Optional['Substitutions'] = None
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
                _sub = Substitutions()
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
        sub: 'Substitutions',
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

    def __str__(self) -> str:
        in_types = ' '.join(map(str, self.input))
        out_types = ' '.join(map(str, self.output))
        return '({} -- {})'.format(in_types, out_types)

    def get_type_of_attribute(self, name: str) -> '_Function':
        if name == '__call__':
            return self
        raise AttributeError(self, name)

    def apply_substitution(self, sub: 'Substitutions') -> '_Function':
        return _Function(sub(self.input), sub(self.output))


class PrimitiveTypes:
    int = PrimitiveType('int')
    bool = PrimitiveType('bool')
    object = PrimitiveType('object')
    context_manager = PrimitiveType('context_manager')
    dict = PrimitiveType('dict')
    module = PrimitiveType('module')
    py_function = PrimitiveType('py_function')
    str = PrimitiveType('str', (), {'__getitem__': py_function})
    list = PrimitiveType('list', (), {'__getitem__': py_function})
    file = PrimitiveType(
        'file', (), {'seek': py_function, 'read': py_function}
    )


class PrimitiveInterfaces:
    invertible = PrimitiveInterface('invertible')
    invertible.add_attribute('__invert__', PrimitiveTypes.py_function)
    iterable = PrimitiveInterface('iterable')
    for type in {
        PrimitiveTypes.int,
        PrimitiveTypes.dict,
        PrimitiveTypes.list,
        PrimitiveTypes.file,
    }:
        type.add_supertype(iterable)


class TypeWithAttribute(IndividualType):
    def __init__(
        self, attribute: str, attribute_type: 'IndividualType'
    ) -> None:
        super().__init__()
        self.attribute = attribute
        self.attribute_type = attribute_type

    def __str__(self) -> str:
        type = ''
        if self.attribute_type is not PrimitiveTypes.object:
            type = ':' + str(self.attribute_type)
        return '.{}'.format(self.attribute) + type

    def get_type_of_attribute(self, name: str) -> 'IndividualType':
        if name != self.attribute:
            raise AttributeError(self, name)
        return self.attribute_type

    def apply_substitution(self, sub: 'Substitutions') -> 'TypeWithAttribute':
        return TypeWithAttribute(self.attribute, sub(self.attribute_type))


StackItemType = Union[SequenceVariable, IndividualType]

# expose _Function as StackEffect
StackEffect = _Function


class Environment(Dict[str, Type]):
    def copy(self) -> 'Environment':
        return Environment(super().copy())

    def apply_substitution(self, sub: 'Substitutions') -> 'Environment':
        return Environment({name: sub(t) for name, t in self.items()})


class Substitutions(Dict[_Variable, Union[Type, List[StackItemType]]]):

    _T = Union['Substitutions', Type, Sequence[StackItemType], Environment]

    @overload
    def __call__(self, arg: 'Substitutions') -> 'Substitutions':
        ...

    @overload
    def __call__(self, arg: PrimitiveType) -> PrimitiveType:
        ...

    @overload
    def __call__(self, arg: _Function) -> _Function:
        ...

    @overload
    def __call__(self, arg: ForAll) -> ForAll:
        ...

    @overload
    def __call__(self, arg: IndividualVariable) -> IndividualType:
        ...

    @overload
    def __call__(self, arg: TypeWithAttribute) -> TypeWithAttribute:
        ...

    @overload
    def __call__(self, arg: _IntersectionType) -> _IntersectionType:
        ...

    @overload
    def __call__(self, arg: PrimitiveInterface) -> PrimitiveInterface:
        ...

    @overload
    def __call__(
        self, arg: SequenceVariable
    ) -> Union[SequenceVariable, List[StackItemType]]:
        ...

    @overload
    def __call__(self, arg: IndividualType) -> IndividualType:
        ...

    @overload
    def __call__(self, arg: Type) -> NoReturn:
        ...

    @overload
    def __call__(self, arg: Sequence[StackItemType]) -> List[StackItemType]:
        ...

    @overload
    def __call__(self, arg: Environment) -> Environment:
        ...

    def __call__(self, arg: '_T') -> '_T':
        if isinstance(arg, collections.abc.Sequence):
            subbed_types: List[StackItemType] = []
            for type in arg:
                subbed_type: Union[StackItemType, List[StackItemType]] = self(
                    type
                )
                if isinstance(subbed_type, list):
                    subbed_types += subbed_type
                else:
                    subbed_types.append(subbed_type)
            return subbed_types
        return arg.apply_substitution(self)

    def _dom(self) -> Set[_Variable]:
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


_InferFunction = Callable[
    [
        Environment,
        'concat.astutils.WordsOrStatements',
        bool,
        Tuple['_InferFunction'],
        Tuple[Substitutions, _Function],
    ],
    Tuple[Substitutions, _Function],
]


def inst(
    sigma: Union[ForAll, PrimitiveInterface, _Function]
) -> IndividualType:
    """This is based on the inst function described by Kleffner."""
    if isinstance(sigma, ForAll):
        subs = Substitutions(
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


def infer(
    gamma: Environment,
    e: 'concat.astutils.WordsOrStatements',
    extensions: Optional[Tuple[_InferFunction]] = None,
    is_top_level=False,
) -> Tuple[Substitutions, _Function]:
    """The infer function described by Kleffner."""
    e = list(e)
    current_subs = Substitutions()
    a_bar = SequenceVariable()
    current_effect = (
        _Function([], []) if is_top_level else _Function([a_bar], [a_bar])
    )

    for node in e:
        try:
            S, (i, o) = current_subs, current_effect

            if isinstance(node, concat.level0.parse.NumberWordNode):
                if isinstance(node.value, int):
                    current_effect = _Function(i, [*o, PrimitiveTypes.int])
                else:
                    raise NotImplementedError
            # there's no False word at the moment
            elif isinstance(node, concat.level1.parse.TrueWordNode):
                current_effect = _Function(i, [*o, PrimitiveTypes.bool])
            elif isinstance(node, concat.level1.operators.AddWordNode):
                # for now, only works with ints and strings
                a_bar = SequenceVariable()
                try:
                    phi = unify(
                        list(o),
                        [a_bar, PrimitiveTypes.int, PrimitiveTypes.int],
                    )
                except TypeError:
                    phi = unify(
                        list(o),
                        [a_bar, PrimitiveTypes.str, PrimitiveTypes.str],
                    )
                    current_subs, current_effect = (
                        phi(S),
                        phi(_Function(i, [a_bar, PrimitiveTypes.str])),
                    )
                else:
                    current_subs, current_effect = (
                        phi(S),
                        phi(_Function(i, [a_bar, PrimitiveTypes.int])),
                    )
            elif isinstance(node, concat.level0.parse.NameWordNode):
                # the type of if_then is built-in
                if node.value == 'if_then':
                    a_bar = SequenceVariable()
                    b = _Function([a_bar], [a_bar])
                    phi = unify(list(o), [a_bar, PrimitiveTypes.bool, b])
                    current_subs, current_effect = (
                        phi(S),
                        phi(_Function(i, [a_bar])),
                    )
                # the type of call is built-in
                elif node.value == 'call':
                    a_bar, b_bar = SequenceVariable(), SequenceVariable()
                    phi = unify(list(o), [a_bar, _Function([a_bar], [b_bar])])
                    current_subs, current_effect = (
                        phi(S),
                        phi(_Function(i, [b_bar])),
                    )
                else:
                    (i1, o1) = i, o
                    if node.value not in S(gamma):
                        raise NameError(node)
                    type_of_name = inst(S(gamma)[node.value].to_for_all())
                    if not isinstance(type_of_name, _Function):
                        raise NotImplementedError(
                            'name {} of type {}'.format(
                                node.value, type_of_name
                            )
                        )
                    i2, o2 = type_of_name
                    phi = unify(list(o1), S(i2))
                    current_subs, current_effect = (
                        phi(S),
                        phi(_Function(i1, S(o2))),
                    )
            elif isinstance(
                node, concat.level0.parse.PushWordNode
            ) and not isinstance(
                node.children[0], concat.level1.parse.SubscriptionWordNode
            ):
                S1, (i1, o1) = S, (i, o)
                # special case for push an attribute accessor
                child = node.children[0]
                rest = SequenceVariable()
                if isinstance(child, concat.level0.parse.AttributeWordNode):
                    attr_type_var = IndividualVariable()
                    top = IndividualVariable(
                        TypeWithAttribute(child.value, attr_type_var)
                    )
                    S2 = unify(list(o1), [rest, top])
                    attr_type = inst(S2(attr_type_var).to_for_all())
                    rest_types = S2([rest])
                    current_subs, current_effect = (
                        S2(S1),
                        _Function(S2(i1), [*rest_types, attr_type]),
                    )
                # special case for name words
                elif isinstance(child, concat.level0.parse.NameWordNode):
                    if child.value not in gamma:
                        raise NameError(child)
                    name_type = inst(gamma[child.value].to_for_all())
                    current_subs, current_effect = (
                        S1,
                        _Function(i1, [*o1, S1(name_type)]),
                    )
                else:
                    S2, (i2, o2) = infer(
                        S1(gamma), node.children, extensions=extensions
                    )
                    current_subs, current_effect = (
                        S2(S1),
                        _Function(S2(i1), [*S2(o1), _Function(i2, o2)]),
                    )
            elif isinstance(node, concat.level0.parse.QuoteWordNode):
                quotation = cast(concat.level0.parse.QuoteWordNode, node)
                S1, (i1, o1) = infer(
                    gamma, [*quotation.children], extensions=extensions
                )
                phi = unify(S1(o), i1)
                current_subs, current_effect = (
                    phi(S1(S)),
                    phi(S1(_Function(i, o1))),
                )
            # there is no fix combinator, lambda abstraction, or a let form like
            # Kleffner's
            # now for our extensions
            elif isinstance(node, concat.level1.parse.WithWordNode):
                a_bar, b_bar = SequenceVariable(), SequenceVariable()
                body_type = _Function([a_bar, PrimitiveTypes.object], [b_bar])
                phi = unify(
                    list(o), [a_bar, body_type, PrimitiveTypes.context_manager]
                )
                current_subs, current_effect = (
                    phi(S),
                    phi(_Function(i, [b_bar])),
                )
            elif isinstance(node, concat.level1.parse.TryWordNode):
                a_bar, b_bar = SequenceVariable(), SequenceVariable()
                phi = unify(
                    list(o),
                    [
                        a_bar,
                        PrimitiveInterfaces.iterable,
                        _Function([a_bar], [b_bar]),
                    ],
                )
                current_subs, current_effect = (
                    phi(S),
                    phi(_Function(i, [b_bar])),
                )
            elif isinstance(node, concat.level1.parse.DictWordNode):
                phi = S
                collected_type = o
                for key, value in node.dict_children:
                    phi1, (i1, o1) = infer(
                        phi(gamma), key, extensions=extensions
                    )
                    R1 = unify(phi1(collected_type), list(i1))
                    phi = R1(phi1(phi))
                    collected_type = phi(o1)
                    # drop the top of the stack to use as the key
                    (
                        collected_type,
                        collected_type_sub,
                    ) = drop_last_from_type_seq(collected_type)
                    phi = collected_type_sub(phi)
                    phi2, (i2, o2) = infer(
                        phi(gamma), value, extensions=extensions
                    )
                    R2 = unify(phi2(collected_type), list(i2))
                    phi = R2(phi2(phi))
                    collected_type = phi(o2)
                    # drop the top of the stack to use as the value
                    (
                        collected_type,
                        collected_type_sub,
                    ) = drop_last_from_type_seq(collected_type)
                    phi = collected_type_sub(phi)
                current_subs, current_effect = (
                    phi,
                    phi(_Function(i, [*collected_type, PrimitiveTypes.dict])),
                )
            elif isinstance(node, concat.level1.parse.ListWordNode):
                phi = S
                collected_type = o
                for item in node.list_children:
                    phi1, (i1, o1) = infer(
                        phi(gamma), item, extensions=extensions
                    )
                    R1 = unify(phi1(phi(collected_type)), list(i1))
                    collected_type = R1(phi1(phi(o1)))
                    # drop the top of the stack to use as the key
                    (
                        collected_type,
                        collected_type_sub,
                    ) = drop_last_from_type_seq(list(collected_type))
                    phi = collected_type_sub(R1(phi1(phi)))
                current_subs, current_effect = (
                    phi,
                    phi(_Function(i, [*collected_type, PrimitiveTypes.list])),
                )
            elif isinstance(node, concat.level1.operators.InvertWordNode):
                out_var = SequenceVariable()
                type_var = IndividualVariable(PrimitiveInterfaces.invertible)
                phi = unify(list(o), [out_var, type_var])
                current_subs, current_effect = (
                    phi(S),
                    phi(_Function(i, [out_var, type_var])),
                )
            elif isinstance(node, concat.level0.parse.StringWordNode):
                current_subs, current_effect = (
                    S,
                    _Function(i, [*o, PrimitiveTypes.str]),
                )
            elif isinstance(node, concat.level0.parse.AttributeWordNode):
                out_var = SequenceVariable()
                attr_type_var = IndividualVariable()
                type_var = IndividualVariable(
                    TypeWithAttribute(node.value, attr_type_var)
                )
                phi = unify(list(o), [out_var, type_var])
                attr_type = phi(attr_type_var)
                if not isinstance(attr_type, _Function):
                    message = '.{} is not a Concat function (has type {})'.format(
                        node.value, attr_type
                    )
                    raise TypeError(message)
                out_types = phi(out_var)
                if isinstance(out_types, SequenceVariable):
                    out_types = [out_types]
                R = unify(out_types, phi([*attr_type.input]))
                current_subs, current_effect = (
                    R(phi(S)),
                    R(phi(_Function(i, attr_type.output))),
                )
            else:
                fail = True
                for extension in extensions or []:
                    try:
                        kwargs = dict(
                            extensions=extensions,
                            previous=(S, _Function(i, o)),
                        )
                        # NOTE: Extension compose their results with the
                        # current effect (the `previous` keyword argument).
                        current_subs, current_effect = extension(
                            gamma, [node], is_top_level, **kwargs
                        )
                        fail = False
                        break
                    except NotImplementedError:
                        pass
                if fail:
                    raise NotImplementedError(
                        "don't know how to handle '{}'".format(node)
                    )
        except TypeError as e:
            e.set_location_if_missing(node.location)
            raise
    return current_subs, current_effect


def _ftv(
    f: Union[Type, List[StackItemType], Dict[str, Type]]
) -> Set[_Variable]:
    """The ftv function described by Kleffner."""
    ftv: Set[_Variable]
    if isinstance(f, (PrimitiveType, PrimitiveInterface)):
        return set()
    elif isinstance(f, _Variable):
        return {f}
    elif isinstance(f, _Function):
        return _ftv(list(f.input)) | _ftv(list(f.output))
    elif isinstance(f, list):
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


def unify(i1: List[StackItemType], i2: List[StackItemType]) -> Substitutions:
    """The unify function described by Kleffner, but with support for subtyping.

    Since subtyping is a directional relation, we say i1 is the input type, and
    i2 is the output type. The subsitutions returned will make i1 a subtype of
    i2. This is inspired by Polymorphism, Subtyping, and Type Inference in
    MLsub (Dolan and Mycroft 2016)."""

    if (len(i1), len(i2)) == (0, 0):
        return Substitutions({})
    if len(i1) == 1:
        if isinstance(i1[0], SequenceVariable) and i1 == i2:
            return Substitutions({})
        elif isinstance(i1[0], SequenceVariable) and i1[0] not in _ftv(i2):
            return Substitutions({i1[0]: [*i2]})
    if (
        len(i2) == 1
        and isinstance(i2[0], SequenceVariable)
        and i2[0] not in _ftv(i1)
    ):
        return Substitutions({i2[0]: [*i1]})
    if (
        len(i1) > 0
        and len(i2) > 0
        and isinstance(i1[-1], IndividualType)
        and isinstance(i2[-1], IndividualType)
    ):
        phi1 = unify_ind(i1[-1], i2[-1])
        phi2 = unify(phi1(i1[:-1]), phi1(i2[:-1]))
        return phi2(phi1)
    raise TypeError(
        'cannot unify {} with {}'.format(
            [str(t) for t in i1], [str(t) for t in i2]
        )
    )


def unify_ind(
    t1: Union[IndividualType, ForAll], t2: Union[IndividualType, ForAll]
) -> Substitutions:
    """A modified version of the unifyInd function described by Kleffner.

    Since subtyping is a directional relation, we say t1 is the input type, and
    t2 is the output type. The subsitutions returned will make t1 a subtype of
    t2. This is inspired by Polymorphism, Subtyping, and Type Inference in
    MLsub (Dolan and Mycroft 2016). Variables can be subsituted in either
    direction."""
    t1 = inst(t1.to_for_all())
    t2 = inst(t2.to_for_all())
    Primitive = (PrimitiveType, PrimitiveInterface)
    if isinstance(t1, PrimitiveInterface) and isinstance(t2, PrimitiveInterface):
        if not t1.is_related_to(t2):
            raise TypeError('{} and {} are not derived from the same interface'.format(t1, t2))
        if t2.type_arguments is None:
            return Substitutions()
        if t1.type_arguments is None:
            raise TypeError('{} has no type arguments, but {} does'.format(t1, t2))
        return unify([*t1.type_arguments], [*t2.type_arguments])
    elif isinstance(t1, PrimitiveType) and isinstance(t2, PrimitiveInterface):
        phi = Substitutions()
        fail = True
        for type in t1.supertypes:
            try:
                phi = unify_ind(type, t2)(phi)
                fail = False
            except TypeError:
                pass
        if fail:
            raise TypeError('{} does not implement {}'.format(t1, t2))
        return phi
    elif isinstance(t1, Primitive) and isinstance(t2, PrimitiveType):
        if not t1.is_subtype_of(t2):
            raise TypeError(
                'Primitive type {} cannot unify with primitive type {}'.format(
                    t1, t2
                )
            )
        return Substitutions()
    elif isinstance(t1, IndividualVariable) and t1 not in _ftv(t2):
        phi = None
        if t1.is_subtype_of(t2):
            if isinstance(t2, IndividualVariable):
                phi = unify_ind(t1.bound, t2.bound)
            else:
                phi = unify_ind(t1.bound, t2)
        if t2.is_subtype_of(t1):
            phi = Substitutions({t1: IndividualVariable(t2)})(
                phi or Substitutions()
            )
        if phi is None:
            if isinstance(t2, IndividualVariable):
                new_var = IndividualVariable(t1.bound & t2.bound)
                phi = Substitutions({t1: new_var, t2: new_var})
            else:
                raise TypeError('{} cannot unify with {}'.format(t1, t2))

        return phi
    elif isinstance(t2, IndividualVariable) and t2 not in _ftv(t1):
        if t1.is_subtype_of(t2):
            phi = Substitutions({t2: t1})
            phi = (unify_ind(phi(t1), phi(t2.bound)))(phi)
            return phi
        raise TypeError('{} cannot unify with {}'.format(t1, t2))
    elif isinstance(t1, _Function) and isinstance(t2, _Function):
        phi1 = unify(list(t2.input), list(t1.input))
        phi2 = unify(list(phi1(t1.output)), list(phi1(t2.output)))
        return phi2(phi1)
    elif isinstance(t1, TypeWithAttribute):
        if t1.is_subtype_of(t2):
            try:
                attr_type = t2.get_type_of_attribute(t1.attribute)
            except TypeError:
                return Substitutions()
            return unify_ind(t1.attribute_type, attr_type)
        raise TypeError('{} cannot unify with {}'.format(t1, t2))
    elif isinstance(t2, TypeWithAttribute):
        attr_type = t1.get_type_of_attribute(t2.attribute)
        return unify_ind(attr_type, t2.attribute_type)
    elif t1.is_subtype_of(t2):
        return Substitutions()
    else:
        raise TypeError('{} cannot unify with {}'.format(t1, t2))


def drop_last_from_type_seq(
    l: List[StackItemType],
) -> Tuple[List[StackItemType], Substitutions]:
    kept = SequenceVariable()
    dropped = IndividualVariable()
    drop_sub = unify(l, [kept, dropped])
    return drop_sub([kept]), drop_sub
