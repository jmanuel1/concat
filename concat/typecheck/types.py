from __future__ import annotations

import abc
import functools
import logging
import operator
from collections.abc import Callable
from typing import (
    TYPE_CHECKING,
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
    Tuple,
    TypeVar,
    Union,
    cast,
    overload,
)

from concat.logging import ConcatLogger
from concat.orderedset import InsertionOrderedSet
from concat.typecheck.errors import AttributeError as ConcatAttributeError
from concat.typecheck.errors import (
    StackMismatchError,
    StaticAnalysisError,
)
from concat.typecheck.errors import TypeError as ConcatTypeError
from concat.typecheck.errors import (
    format_attributes_unknown_error,
    format_cannot_have_attributes_error,
    format_generic_type_attributes_error,
    format_item_type_expected_in_type_sequence_error,
    format_must_be_item_type_error,
    format_not_a_nominal_type_error,
    format_not_allowed_as_overload_error,
    format_not_generic_type_error,
    format_occurs_error,
    format_rigid_variable_error,
    format_subkinding_error,
    format_subtyping_error,
    format_type_tuple_index_out_of_range_error,
    format_unknown_sequence_type,
    format_wrong_arg_kind_error,
    format_wrong_number_of_type_arguments_error,
)
from concat.typecheck.substitutions import Substitutions

if TYPE_CHECKING:
    from concat.typecheck import TypeChecker
    from concat.typecheck.env import Environment


_logger = ConcatLogger(logging.getLogger())


def _sub_cache[T: Type, R](
    f: Callable[[T, Substitutions], R],
) -> Callable[[T, Substitutions], T | R]:
    _sub_cache = dict[tuple[int, int], T | R]()

    def apply_substitution(self: T, sub: Substitutions) -> T | R:
        if (self._type_id, sub.id) not in _sub_cache:
            if not (set(sub) & self.free_type_variables()):
                _sub_cache[self._type_id, sub.id] = self
            else:
                _sub_cache[self._type_id, sub.id] = f(self, sub)
        return _sub_cache[self._type_id, sub.id]

    return apply_substitution


class Type(abc.ABC):
    _next_type_id = 0
    the_object_type_id = -1

    def __init__(self) -> None:
        self._free_type_variables_cached: Optional[
            InsertionOrderedSet[Variable]
        ] = None
        self._internal_name: Optional[str] = None
        self._type_id = Type._next_type_id
        Type._next_type_id += 1

    def unsafe_set_type_id(self, identifier: int) -> None:
        self._type_id = identifier

    # No <= implementation using subtyping, because variables overload that for
    # sort by identity.

    def __eq__(self, _) -> bool:
        return NotImplemented

    # QUESTION: Remove? I think this is used only in tests, since it doesn't
    # return the substitutions and the error it's less convenient to debug a
    # test.
    def equals(self, context: TypeChecker, other: object) -> bool:
        if self is other:
            return True
        if not isinstance(other, Type):
            return NotImplemented
        # QUESTION: Define == separately from subtyping code?
        ftv = self.free_type_variables() | other.free_type_variables()
        try:
            subtype_sub = self.constrain_and_bind_variables(
                context, other, set(), []
            )
            supertype_sub = other.constrain_and_bind_variables(
                context, self, set(), []
            )
        except StaticAnalysisError:
            return False
        subtype_sub = Substitutions(
            {v: t for v, t in subtype_sub.items() if v in ftv}
        )
        supertype_sub = Substitutions(
            {v: t for v, t in supertype_sub.items() if v in ftv}
        )
        return not subtype_sub and not supertype_sub

    # NOTE: Avoid hashing types. I'm having correctness issues related to
    # hashing that I'd rather avoid entirely. Maybe one day I'll introduce hash
    # consing, but that would only reflect syntactic eequality, and I've been
    # using hashing for type equality.

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

    @_sub_cache
    def apply_substitution(self, sub: Substitutions) -> 'Type':
        return DelayedSubstitution(sub, self)

    @abc.abstractmethod
    def force_substitution(self, _: Substitutions) -> 'Type':
        pass

    @abc.abstractmethod
    def constrain_and_bind_variables(
        self,
        context: TypeChecker,
        supertype: 'Type',
        rigid_variables: AbstractSet['Variable'],
        subtyping_assumptions: List[Tuple['Type', 'Type']],
    ) -> 'Substitutions':
        raise NotImplementedError

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

    @abc.abstractmethod
    def force_repr(self) -> str:
        pass

    def __getitem__(self, _: Any) -> Type:
        _logger.debug('tried to treat {} as generic or sequence', self)
        raise ConcatTypeError(
            f'{self} is neither a generic type nor a sequence type',
            is_occurs_check_fail=None,
            rigid_variables=None,
        )

    def apply_is_redex(_) -> bool:
        return False

    def force_apply(self, args: Any) -> Type:
        return self[args]

    def project(self, i: int) -> Type:
        return Projection(self, i)

    def project_is_redex(_) -> bool:
        return False

    def force_project(self, i: int) -> Type:
        return self.project(i)

    @property
    def brand(self) -> Brand:
        raise ConcatTypeError(
            format_not_a_nominal_type_error(self),
            is_occurs_check_fail=None,
            rigid_variables=None,
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


class TypeApplication(Type):
    def __init__(self, head: Type, args: 'TypeArguments') -> None:
        super().__init__()
        if not isinstance(head.kind, GenericTypeKind):
            raise ConcatTypeError(
                format_not_generic_type_error(head),
                is_occurs_check_fail=None,
                rigid_variables=None,
            )
        if len(head.kind.parameter_kinds) == 1 and isinstance(
            head.kind.parameter_kinds[0], VariableArgumentKind
        ):
            args = [VariableArgumentPack.collect_arguments(args)]
        if len(args) != len(head.kind.parameter_kinds):
            raise ConcatTypeError(
                format_wrong_number_of_type_arguments_error(
                    len(head.kind.parameter_kinds), len(args)
                ),
                is_occurs_check_fail=None,
                rigid_variables=None,
            )
        for i, (arg, param_kind) in enumerate(
            zip(args, head.kind.parameter_kinds)
        ):
            if not (arg.kind <= param_kind):
                raise ConcatTypeError(
                    format_wrong_arg_kind_error(head, i, arg, param_kind),
                    is_occurs_check_fail=None,
                    rigid_variables=None,
                )
        self._head = head
        self._args = args
        self._result_kind = head.kind.result_kind
        self._forced: Type | None = None

    @property
    def attributes(self) -> NoReturn:
        raise ConcatTypeError(
            format_attributes_unknown_error(self),
            is_occurs_check_fail=None,
            rigid_variables=None,
        )

    @property
    def kind(self) -> Kind:
        return self._result_kind

    def force_substitution(self, sub: 'Substitutions') -> Type:
        forced = self._head.force_substitution(sub)[
            [sub(t) for t in self._args]
        ]
        if isinstance(forced, DelayedSubstitution):
            return forced.force()
        return forced

    def constrain_and_bind_variables(
        self,
        context: TypeChecker,
        supertype,
        rigid_variables,
        subtyping_assumptions,
    ) -> 'Substitutions':
        if isinstance(supertype, DelayedSubstitution):
            supertype = supertype.force()
        if (
            self._type_id == supertype._type_id
            or (
                self._result_kind <= IndividualKind
                and supertype._type_id == context.object_type._type_id
            )
            or _contains_assumption(subtyping_assumptions, self, supertype)
        ):
            return Substitutions()
        if isinstance(supertype, TypeApplication):
            # TODO: Variance
            return self._head.constrain_and_bind_variables(
                context,
                supertype._head,
                rigid_variables,
                subtyping_assumptions,
            )
        # occurs check!
        if (
            isinstance(supertype, Variable)
            and supertype.kind >= self.kind
            and supertype not in rigid_variables
        ):
            if supertype in self.free_type_variables():
                raise ConcatTypeError(
                    format_occurs_error(supertype, self),
                    is_occurs_check_fail=True,
                    rigid_variables=rigid_variables,
                )
            return Substitutions([(supertype, self)])
        if self._head.apply_is_redex():
            return self.force().constrain_and_bind_variables(
                context, supertype, rigid_variables, subtyping_assumptions
            )
        raise ConcatTypeError(
            f'Cannot deduce that {self} is a subtype of {supertype} here',
            is_occurs_check_fail=False,
            rigid_variables=rigid_variables,
        )

    def is_redex(self) -> bool:
        return self._head.apply_is_redex()

    def force(self) -> Type:
        if not self._forced:
            self._forced = self._head.force_apply(self._args)
        return self._forced

    def __str__(self) -> str:
        if self._internal_name is not None:
            return self._internal_name
        return f'{self._head}{_iterable_to_str(self._args)}'

    def __repr__(self) -> str:
        return f'TypeApplication({self._head!r}, {self._args!r})'

    def force_repr(self) -> str:
        if self.is_redex():
            return self.force().force_repr()
        return f'TypeApplication({self._head.force_repr()}, {[a.force_repr() for a in self._args]})'

    def _free_type_variables(self) -> InsertionOrderedSet['Variable']:
        ftv = self._head.free_type_variables()
        for arg in self._args:
            ftv |= arg.free_type_variables()
        return ftv

    @property
    def brand(self) -> Brand:
        return self._head.brand


# QUESTION: How to avoid showing type tuple-related syntax in error messages?
class Projection(Type):
    def __init__(self, head: Type, i: int) -> None:
        super().__init__()
        # type tuples are an internal feature
        assert isinstance(head.kind, TupleKind)
        assert 0 <= i < len(head.kind.element_kinds)
        self._head = head
        self._index = i
        self._kind = head.kind.element_kinds[i]
        self._forced: Type | None = None

    def _free_type_variables(self) -> InsertionOrderedSet[Variable]:
        if self.is_redex():
            return self.force().free_type_variables()
        return self._head.free_type_variables()

    def force_substitution(self, sub: Substitutions) -> Type:
        return self._head.force_substitution(sub).project(self._index)

    @property
    def attributes(self) -> Mapping[str, Type]:
        if self._head.project_is_redex():
            return self.force().attributes
        raise ConcatTypeError(
            format_attributes_unknown_error(self),
            is_occurs_check_fail=None,
            rigid_variables=None,
        )

    def constrain_and_bind_variables(
        self, context, supertype, rigid_variables, subtyping_assumptions
    ) -> Substitutions:
        if self._type_id == supertype._type_id or _contains_assumption(
            subtyping_assumptions, self, supertype
        ):
            return Substitutions()
        if isinstance(supertype, Projection):
            sub = self._head.constrain_and_bind_variables(
                context,
                supertype._head,
                rigid_variables,
                subtyping_assumptions,
            )
            assert self._index == supertype._index, format_subtyping_error(
                self,
                supertype,
            )
            return sub
        if self._head.project_is_redex():
            return self.force().constrain_and_bind_variables(
                context, supertype, rigid_variables, subtyping_assumptions
            )
        raise ConcatTypeError(
            format_subtyping_error(self, supertype),
            is_occurs_check_fail=None,
            rigid_variables=rigid_variables,
        )

    @property
    def kind(self) -> Kind:
        return self._kind

    def __getitem__(self, x: Any) -> Any:
        if self._kind <= SequenceKind:
            if self._head.project_is_redex():
                return self.force()[x]
            raise ConcatTypeError(
                format_unknown_sequence_type(self),
                is_occurs_check_fail=None,
                rigid_variables=None,
            )
        return TypeApplication(self, x)

    def apply_is_redex(self) -> bool:
        return True

    def force_apply(self, args: TypeArguments) -> Type:
        return self.force()[args]

    def is_redex(self) -> bool:
        return self._head.project_is_redex()

    def force(self) -> Type:
        if not self._forced:
            self._forced = self._head.force_project(self._index)
        return self._forced

    @property
    def brand(self) -> Brand:
        if self.is_redex():
            return self.force().brand
        return super().brand

    def __repr__(self) -> str:
        return f'Projection({self._head!r}, {self._index!r})'

    def force_repr(self) -> str:
        if self.is_redex():
            return self.force().force_repr()
        return f'Projection({self._head.force_repr()}, {self._index!r})'

    def __str__(self) -> str:
        if self.is_redex():
            return str(self.force())
        return f'{self._head}.{self._index}'


class Variable(Type, abc.ABC):
    """Objects that represent type variables.

    Every type variable object is assumed to be unique. Thus, fresh type
    variables can be made simply by creating new objects. They can also be
    compared by identity."""

    @_sub_cache
    def apply_substitution(self, sub: Substitutions) -> Type:
        if self in sub:
            result = sub[self]
            return result
        return self

    def force_substitution(self, sub: Substitutions) -> Type:
        result = self.apply_substitution(sub)
        if isinstance(result, DelayedSubstitution):
            return result.force()
        return result

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

    def __str__(self) -> str:
        return f't_{id(self)}'

    def force_repr(self) -> str:
        return repr(self)

    def __getitem__(self, args: 'TypeArguments') -> Type:
        # TypeApplication will do kind checking
        return TypeApplication(self, args)


class BoundVariable(Variable):
    def __init__(self, kind: 'Kind') -> None:
        super().__init__()
        self._kind = kind

    @property
    def kind(self) -> 'Kind':
        return self._kind

    def constrain_and_bind_variables(
        self, context, supertype, rigid_variables, subtyping_assumptions
    ) -> 'Substitutions':
        if (
            self._type_id == supertype._type_id
            or (
                self.kind >= IndividualKind
                and supertype._type_id == context.object_type._type_id
            )
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
            f'Cannot constrain bound variable {self} to {supertype}',
            is_occurs_check_fail=None,
            rigid_variables=rigid_variables,
        )

    def __repr__(self) -> str:
        return f'<bound variable {id(self)}>'

    def __str__(self) -> str:
        return f't_{id(self)} : {self._kind}'

    @property
    def attributes(self) -> Mapping[str, Type]:
        raise TypeError('Cannot get attributes of bound variables')

    def freshen(self) -> 'Variable':
        if self._kind <= ItemKind:
            return ItemVariable(self._kind)
        if isinstance(self._kind, VariableArgumentKind):
            return VariableArgumentVariable(self._kind.argument_kind)
        if self._kind is SequenceKind:
            return SequenceVariable()
        raise NotImplementedError


class ItemVariable(Variable):
    def __init__(self, kind: 'Kind') -> None:
        assert kind <= ItemKind
        super().__init__()
        self._kind = kind

    def constrain_and_bind_variables(
        self,
        context: TypeChecker,
        supertype: Type,
        rigid_variables: AbstractSet['Variable'],
        subtyping_assumptions: List[Tuple['Type', 'Type']],
    ) -> 'Substitutions':
        if isinstance(supertype, DelayedSubstitution):
            supertype = supertype.force()
        if (
            self._type_id == supertype._type_id
            or supertype._type_id == context.object_type._type_id
            or _contains_assumption(subtyping_assumptions, self, supertype)
        ):
            return Substitutions()
        if (
            isinstance(supertype, Variable)
            and self.kind <= supertype.kind
            and supertype not in rigid_variables
        ):
            return Substitutions([(supertype, self)])
        mapping: Mapping[Variable, Type]
        if isinstance(supertype, _OptionalType):
            try:
                return self.constrain_and_bind_variables(
                    context,
                    supertype.type_arguments[0],
                    rigid_variables,
                    subtyping_assumptions,
                )
            except ConcatTypeError:
                return self.constrain_and_bind_variables(
                    context,
                    context.none_type,
                    rigid_variables,
                    subtyping_assumptions,
                )
        if self in rigid_variables:
            raise ConcatTypeError(
                format_rigid_variable_error(self, supertype),
                is_occurs_check_fail=False,
                rigid_variables=rigid_variables,
            )
        if self.kind >= supertype.kind:
            # FIXME: occurs check!
            mapping = {self: supertype}
            return Substitutions(mapping)
        raise ConcatTypeError(
            format_subkinding_error(supertype, self),
            is_occurs_check_fail=False,
            rigid_variables=rigid_variables,
        )

    def __str__(self) -> str:
        return 't_{}'.format(id(self))

    def __repr__(self) -> str:
        return '<item variable {}>'.format(id(self))

    @property
    def attributes(self) -> NoReturn:
        raise ConcatTypeError(
            f'{self} is an item type variable, so its attributes are unknown',
            is_occurs_check_fail=None,
            rigid_variables=None,
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
        context: TypeChecker,
        supertype: Type,
        rigid_variables: AbstractSet['Variable'],
        subtyping_assumptions: List[Tuple['Type', 'Type']],
    ) -> 'Substitutions':
        if not (supertype.kind <= SequenceKind):
            raise ConcatTypeError(
                '{} must be a sequence type, not {}'.format(self, supertype),
                is_occurs_check_fail=False,
                rigid_variables=rigid_variables,
            )
        if isinstance(supertype, DelayedSubstitution):
            supertype = supertype.force()
        if (
            isinstance(supertype, SequenceVariable)
            and supertype not in rigid_variables
        ):
            sub = Substitutions([(supertype, self)])
            sub.add_subtyping_provenance((self, supertype))
            return sub
        if self in rigid_variables:
            raise ConcatTypeError(
                format_rigid_variable_error(self, supertype),
                is_occurs_check_fail=False,
                rigid_variables=rigid_variables,
            )
        # occurs check
        if self is not supertype and self in supertype.free_type_variables():
            raise ConcatTypeError(
                format_occurs_error(self, supertype),
                is_occurs_check_fail=True,
                rigid_variables=rigid_variables,
            )
        sub = Substitutions([(self, supertype)])
        sub.add_subtyping_provenance((self, supertype))
        return sub

    @property
    def attributes(self) -> NoReturn:
        raise ConcatTypeError(
            'the sequence type {} does not hold attributes'.format(self),
            is_occurs_check_fail=None,
            rigid_variables=None,
        )

    @property
    def kind(self) -> 'Kind':
        return SequenceKind

    def freshen(self) -> 'SequenceVariable':
        return SequenceVariable()


class VariableArgumentVariable(Variable):
    """Type variables that stand for variable-length lists of types."""

    def __init__(self, argument_kind: Kind) -> None:
        super().__init__()
        self._argument_kind = argument_kind

    def __repr__(self) -> str:
        return f'<vararg variable {id(self)}>'

    def constrain_and_bind_variables(
        self,
        context: TypeChecker,
        supertype,
        rigid_variables,
        subtyping_assumptions,
    ) -> Substitutions:
        if self._type_id == supertype._type_id or _contains_assumption(
            subtyping_assumptions, self, supertype
        ):
            return Substitutions()
        # FIXME: Implement occurs check everywhere it should happen.
        if (
            self.kind >= supertype.kind
            and self not in rigid_variables
            and self not in supertype.free_type_variables()
        ):
            return Substitutions([(self, supertype)])
        if (
            isinstance(supertype, Variable)
            and self.kind <= supertype.kind
            and supertype not in rigid_variables
        ):
            return Substitutions([(supertype, self)])
        raise ConcatTypeError(
            format_subtyping_error(self, supertype),
            is_occurs_check_fail=False,
            rigid_variables=rigid_variables,
        )

    @property
    def attributes(self) -> NoReturn:
        raise TypeError('Cannot get attributes of vararg variables')

    @property
    def kind(self) -> VariableArgumentKind:
        return VariableArgumentKind(self._argument_kind)

    def freshen(self) -> VariableArgumentVariable:
        return VariableArgumentVariable(self._argument_kind)


class GenericType(Type):
    def __init__(
        self,
        type_parameters: Sequence['Variable'],
        body: Type,
    ) -> None:
        super().__init__()
        assert type_parameters
        self._type_parameters = type_parameters
        self._body = body
        self._instantiations: Dict[Tuple[int, ...], Type] = {}
        self.is_variadic = type_parameters and isinstance(
            type_parameters[0].kind, VariableArgumentKind
        )

    def __str__(self) -> str:
        if self._internal_name is not None:
            return self._internal_name
        if self.is_variadic:
            params = str(self._type_parameters[0]) + '...'
        else:
            params = ' '.join(map(str, self._type_parameters))

        return f'forall {params}. {self._body}'

    def __repr__(self) -> str:
        return f'GenericType({self._type_parameters!r}, {self._body!r})'

    def force_repr(self) -> str:
        return f'GenericType({_iterable_to_str(t.force_repr() for t in self._type_parameters)}, {self._body.force_repr()})'

    def __getitem__(self, type_arguments: 'TypeArguments') -> 'Type':
        type_argument_ids = tuple(t._type_id for t in type_arguments)
        if type_argument_ids in self._instantiations:
            return self._instantiations[type_argument_ids]
        expected_kinds = [var.kind for var in self._type_parameters]
        if self.is_variadic:
            type_arguments = [
                VariableArgumentPack.collect_arguments(type_arguments)
            ]
        actual_kinds = [ty.kind for ty in type_arguments]
        if len(expected_kinds) != len(actual_kinds):
            raise ConcatTypeError(
                format_wrong_number_of_type_arguments_error(
                    len(expected_kinds), len(actual_kinds)
                ),
                is_occurs_check_fail=None,
                rigid_variables=None,
            )
        for i, (expected_kind, actual_kind) in enumerate(
            zip(expected_kinds, actual_kinds),
        ):
            if not (expected_kind >= actual_kind):
                raise ConcatTypeError(
                    format_subkinding_error(
                        self._type_parameters[i],
                        type_arguments[i],
                    ),
                    is_occurs_check_fail=None,
                    rigid_variables=None,
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
        context: TypeChecker,
        supertype: 'Type',
        rigid_variables: AbstractSet['Variable'],
        subtyping_assumptions: List[Tuple['Type', 'Type']],
    ) -> 'Substitutions':
        if isinstance(supertype, DelayedSubstitution):
            supertype = supertype.force()
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
        if isinstance(supertype, Projection) and supertype.is_redex():
            return self.constrain_and_bind_variables(
                context,
                supertype.force(),
                rigid_variables,
                subtyping_assumptions,
            )
        if not isinstance(supertype, GenericType):
            supertype_parameter_kinds: list[Kind]
            if isinstance(supertype.kind, GenericTypeKind):
                supertype_parameter_kinds = [*supertype.kind.parameter_kinds]
            elif self.kind.result_kind <= supertype.kind:
                supertype_parameter_kinds = []
            else:
                raise ConcatTypeError(
                    format_subkinding_error(self, supertype),
                    is_occurs_check_fail=None,
                    rigid_variables=rigid_variables,
                )
            params_to_inst = len(self.kind.parameter_kinds) - len(
                supertype_parameter_kinds
            )
            if params_to_inst == 0:
                fresh_args = [t.freshen() for t in self._type_parameters]
                return self[fresh_args].constrain_and_bind_variables(
                    context,
                    supertype[fresh_args],
                    rigid_variables,
                    subtyping_assumptions,
                )

            param_kinds_left = [
                *self.kind.parameter_kinds[-len(supertype_parameter_kinds) :]
            ]
            if params_to_inst < 0 or not (
                param_kinds_left >= supertype_parameter_kinds
            ):
                raise ConcatTypeError(
                    format_subkinding_error(self, supertype),
                    is_occurs_check_fail=None,
                    rigid_variables=rigid_variables,
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
                context, supertype, rigid_variables, subtyping_assumptions
            )
        # supertype is a GenericType
        if any(
            map(
                lambda t: t in self.free_type_variables(),
                supertype._type_parameters,
            )
        ):
            raise ConcatTypeError(
                f'Type parameters {
                    supertype._type_parameters
                } cannot appear free in {self}',
                is_occurs_check_fail=True,
                rigid_variables=rigid_variables,
            )
        return self.instantiate().constrain_and_bind_variables(
            context,
            supertype._body,
            rigid_variables | set(supertype._type_parameters),
            subtyping_assumptions,
        )

    def force_substitution(self, sub: 'Substitutions') -> 'GenericType':
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
        )
        return ty

    @property
    def attributes(self) -> NoReturn:
        raise ConcatTypeError(
            format_generic_type_attributes_error(self),
            is_occurs_check_fail=None,
            rigid_variables=None,
        )

    def _free_type_variables(self) -> InsertionOrderedSet['Variable']:
        return self._body.free_type_variables() - set(self._type_parameters)


# TODO: Change representation to a tree or a linked list? Flattening code is
# ugly.
class TypeSequence(Type, Iterable[Type]):
    def __init__(self, sequence: Sequence[Type]) -> None:
        super().__init__()
        while any(
            isinstance(t, DelayedSubstitution) and t.kind <= SequenceKind
            for t in sequence
        ):
            flattened: list[Type] = []
            for t in sequence:
                if (
                    isinstance(t, DelayedSubstitution)
                    and t.kind <= SequenceKind
                ):
                    t = t.force()
                    if isinstance(t, TypeSequence):
                        flattened.extend(t)
                        continue
                flattened.append(t)
            sequence = flattened
        self._rest: Variable | None
        if sequence and sequence[0].kind is SequenceKind:
            if isinstance(sequence[0], Variable):
                self._rest = sequence[0]
            else:
                raise ConcatTypeError(
                    format_item_type_expected_in_type_sequence_error(
                        sequence[0]
                    ),
                    is_occurs_check_fail=None,
                    rigid_variables=None,
                )
            self._individual_types = sequence[1:]
        else:
            self._rest = None
            self._individual_types = sequence
        for ty in self._individual_types:
            if not (ty.kind <= ItemKind):
                raise ConcatTypeError(
                    format_item_type_expected_in_type_sequence_error(ty),
                    is_occurs_check_fail=None,
                    rigid_variables=None,
                )

    def as_sequence(self) -> Sequence[Type]:
        if self._rest is not None:
            return [self._rest, *self._individual_types]
        return self._individual_types

    def force_substitution(self, sub) -> 'TypeSequence':
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
        context: TypeChecker,
        supertype: Type,
        rigid_variables: AbstractSet['Variable'],
        subtyping_assumptions: List[Tuple['Type', 'Type']],
    ) -> 'Substitutions':
        """Check that self is a subtype of supertype.

        Free type variables that appear in either type sequence are set to be
        equal to their counterparts in the other sequence so that type
        information can be propagated into calls of named functions.
        """
        if self is supertype or _contains_assumption(
            subtyping_assumptions, self, supertype
        ):
            sub = Substitutions()
            sub.add_subtyping_provenance((self, supertype))
            return sub

        if isinstance(supertype, DelayedSubstitution):
            supertype = supertype.force()

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
                    raise StackMismatchError(
                        self,
                        supertype,
                        is_occurs_check_fail=None,
                        rigid_variables=rigid_variables,
                    )
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
                raise StackMismatchError(
                    self,
                    supertype,
                    is_occurs_check_fail=None,
                    rigid_variables=rigid_variables,
                )
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
                    context,
                    supertype._individual_types[-1],
                    rigid_variables,
                    subtyping_assumptions,
                )
                try:
                    sub = sub(self[:-1]).constrain_and_bind_variables(
                        context,
                        sub(supertype[:-1]),
                        rigid_variables,
                        subtyping_assumptions,
                    )(sub)
                    return sub
                except StackMismatchError as e:
                    # TODO: Add info about occurs check and rigid
                    # variables.
                    raise StackMismatchError(
                        self,
                        supertype,
                        e.is_occurs_check_fail,
                        rigid_variables,
                    )
            else:
                raise StackMismatchError(
                    self,
                    supertype,
                    is_occurs_check_fail=None,
                    rigid_variables=rigid_variables,
                )
        else:
            raise ConcatTypeError(
                f'{self} is a sequence type, not {supertype}',
                is_occurs_check_fail=None,
                rigid_variables=rigid_variables,
            )

    def _free_type_variables(self) -> InsertionOrderedSet['Variable']:
        ftv: InsertionOrderedSet[Variable] = InsertionOrderedSet([])
        for t in self:
            ftv |= t.free_type_variables()
        return ftv

    @property
    def attributes(self) -> NoReturn:
        raise ConcatTypeError(
            'the sequence type {} does not hold attributes'.format(self),
            is_occurs_check_fail=None,
            rigid_variables=None,
        )

    def __bool__(self) -> bool:
        return not self._is_empty()

    def __len__(self) -> int:
        return len(self.as_sequence())

    def _is_empty(self) -> bool:
        return self._rest is None and not self._individual_types

    @overload
    def __getitem__(self, key: int) -> 'StackItemType': ...

    @overload
    def __getitem__(self, key: slice) -> 'TypeSequence': ...

    def __getitem__(self, key: Union[int, slice]) -> Type:
        if isinstance(key, int):
            return self.as_sequence()[key]
        return TypeSequence(self.as_sequence()[key])

    def __str__(self) -> str:
        return '[' + ', '.join(str(t) for t in self) + ']'

    def __repr__(self) -> str:
        return 'TypeSequence([' + ', '.join(repr(t) for t in self) + '])'

    def force_repr(self) -> str:
        return (
            'TypeSequence([' + ', '.join(t.force_repr() for t in self) + '])'
        )

    def __iter__(self) -> Iterator[Type]:
        return iter(self.as_sequence())

    @property
    def kind(self) -> 'Kind':
        return SequenceKind


class StackEffect(IndividualType):
    """Types of functions that operate on the stack.

    Consists of an input stack type (sequence-kinded) and an output stack type
    (sequence-kinded).
    """

    def __init__(
        self,
        input_types: TypeSequence,
        output_types: TypeSequence,
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
        context: TypeChecker,
        supertype: Type,
        rigid_variables: AbstractSet['Variable'],
        subtyping_assumptions: List[Tuple['Type', 'Type']],
    ) -> 'Substitutions':
        if isinstance(supertype, DelayedSubstitution):
            supertype = supertype.force()
        if (
            self is supertype
            or _contains_assumption(subtyping_assumptions, self, supertype)
            or supertype._type_id == Type.the_object_type_id
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
                context,
                supertype.type_arguments[0],
                rigid_variables,
                subtyping_assumptions,
            )
        if not isinstance(supertype, StackEffect):
            raise ConcatTypeError(
                '{} is not a subtype of {}'.format(self, supertype),
                is_occurs_check_fail=None,
                rigid_variables=rigid_variables,
            )
        # Remember that the input should be contravariant!
        sub = supertype.input.constrain_and_bind_variables(
            context, self.input, rigid_variables, subtyping_assumptions
        )
        sub = sub(self.output).constrain_and_bind_variables(
            context,
            sub(supertype.output),
            rigid_variables,
            subtyping_assumptions,
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
        sub: Substitutions,
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
        return 'StackEffect({!r}, {!r})'.format(self.input, self.output)

    def force_repr(self) -> str:
        return f'StackEffect({self.input.force_repr()}, {self.output.force_repr()})'

    def __str__(self) -> str:
        in_types = ' '.join(map(str, self.input))
        out_types = ' '.join(map(str, self.output))
        return '({} -- {})'.format(in_types, out_types)

    @property
    def attributes(self) -> Mapping[str, 'StackEffect']:
        return {'__call__': self}

    def force_substitution(self, sub: Substitutions) -> 'StackEffect':
        return StackEffect(sub(self.input), sub(self.output))

    def bind(self) -> 'StackEffect':
        return StackEffect(self.input[:-1], self.output)


# QUESTION: Do I use this?
class QuotationType(StackEffect):
    def __init__(self, fun_type: StackEffect) -> None:
        super().__init__(fun_type.input, fun_type.output)

    def constrain_and_bind_variables(
        self,
        context: TypeChecker,
        supertype: Type,
        rigid_variables: AbstractSet['Variable'],
        subtyping_assumptions: List[Tuple['Type', 'Type']],
    ) -> 'Substitutions':
        try:
            # FIXME: Don't present new variables every time.
            # FIXME: Account for the types of the elements of the quotation.
            in_var = ItemVariable(IndividualKind)
            out_var = ItemVariable(IndividualKind)
            quotation_iterable_type = iterable_type[
                StackEffect(TypeSequence([in_var]), TypeSequence([out_var])),
            ]
            return quotation_iterable_type.constrain_and_bind_variables(
                context, supertype, rigid_variables, subtyping_assumptions
            )
        except ConcatTypeError:
            return super().constrain_and_bind_variables(
                context, supertype, rigid_variables, subtyping_assumptions
            )

    @_sub_cache
    def apply_substitution(self, sub: Substitutions) -> 'QuotationType':
        return QuotationType(super().apply_substitution(sub))

    def __repr__(self) -> str:
        return f'QuotationType({StackEffect(self.input, self.output)!r})'

    def force_repr(self) -> str:
        return f'QuotationType({StackEffect(self.input, self.output).force_repr()})'


StackItemType = Union[SequenceVariable, IndividualType]


def free_type_variables_of_mapping(
    attributes: Mapping[str, Type],
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
    return any(
        sub._type_id == subtype._type_id and sup._type_id == supertype._type_id
        for sub, sup in assumptions
    )


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
        self._superbrands = superbrands

    def __str__(self) -> str:
        return self._user_name

    def __repr__(self) -> str:
        return f'Brand({self._user_name!r}, {self.kind!r}, {self._superbrands!r})@{id(self)}'

    def is_subrand_of(self, context: TypeChecker, other: Brand) -> bool:
        object_brand = context.object_type.brand
        return (
            self is other
            or other is object_brand
            or other in self._superbrands
            or any(
                brand.is_subrand_of(context, other)
                for brand in self._superbrands
            )
        )


class NominalType(Type):
    def __init__(self, brand: Brand, ty: Type) -> None:
        super().__init__()

        self._brand = brand
        self._ty = ty
        # TODO: Make sure brands interact with generics properly

    def _free_type_variables(self) -> InsertionOrderedSet[Variable]:
        return self._ty.free_type_variables()

    def force_substitution(self, sub: 'Substitutions') -> 'NominalType':
        return NominalType(self._brand, sub(self._ty))

    def __getitem__(self, args: TypeArguments) -> Type:
        # Since these types are compared by name, we don't need to perform
        # substitution. Just remember the arguments.
        return TypeApplication(self, args)

    def apply_is_redex(self) -> bool:
        return True

    def force_apply(self, args: TypeArguments) -> Type:
        return NominalType(self._brand, self._ty[args])

    @property
    def attributes(self) -> Mapping[str, Type]:
        return self._ty.attributes

    def constrain_and_bind_variables(
        self,
        context: TypeChecker,
        supertype,
        rigid_variables,
        subtyping_assumptions,
    ) -> 'Substitutions':
        _logger.debug('{} <:? {}', self, supertype)
        if (
            self._type_id == supertype._type_id
            or _contains_assumption(subtyping_assumptions, self, supertype)
            or supertype._type_id == Type.the_object_type_id
        ):
            return Substitutions()
        if isinstance(supertype, NominalType):
            if self._brand.is_subrand_of(context, supertype._brand):
                return Substitutions()
            raise ConcatTypeError(
                f'{self} is not a subtype of {supertype}',
                is_occurs_check_fail=None,
                rigid_variables=rigid_variables,
            )
        # TODO: Find a way to force myself to handle these different cases.
        # Visitor pattern? singledispatch?
        if isinstance(supertype, _OptionalType):
            try:
                return self.constrain_and_bind_variables(
                    context,
                    context.none_type,
                    rigid_variables,
                    subtyping_assumptions,
                )
            except ConcatTypeError:
                return self.constrain_and_bind_variables(
                    context,
                    supertype.type_arguments[0],
                    rigid_variables,
                    subtyping_assumptions,
                )
        if isinstance(supertype, Fix):
            return self.constrain_and_bind_variables(
                context,
                supertype.unroll(),
                rigid_variables,
                subtyping_assumptions + [(self, supertype)],
            )
        if isinstance(supertype, Variable):
            if supertype in rigid_variables:
                raise ConcatTypeError(
                    f'{self} is not a subtype of rigid variable {supertype}',
                    is_occurs_check_fail=False,
                    rigid_variables=rigid_variables,
                )
            if not (self.kind <= supertype.kind):
                raise ConcatTypeError(
                    f'{self} has kind {self.kind}, but {supertype} has kind {
                        supertype.kind
                    }',
                    is_occurs_check_fail=False,
                    rigid_variables=rigid_variables,
                )
            return Substitutions([(supertype, self)])
        if (
            isinstance(supertype, (TypeApplication, Projection))
            and supertype.is_redex()
            or isinstance(supertype, DelayedSubstitution)
        ):
            sub = self.constrain_and_bind_variables(
                context,
                supertype.force(),
                rigid_variables,
                subtyping_assumptions,
            )
            sub.add_subtyping_provenance((self, supertype))
            return sub
        return self._ty.constrain_and_bind_variables(
            context, supertype, rigid_variables, subtyping_assumptions
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

    def force_repr(self) -> str:
        return f'NominalType({self._brand!r}, {self._ty.force_repr()})'


class ObjectType(IndividualType):
    """Structural record types."""

    def __init__(self, attributes: Mapping[str, Type]) -> None:
        super().__init__()

        self._attributes = attributes

    @property
    def kind(self) -> 'Kind':
        return IndividualKind

    def force_substitution(
        self,
        sub: Substitutions,
    ) -> 'ObjectType':
        attributes = cast(
            Dict[str, IndividualType],
            {attr: sub(t) for attr, t in self._attributes.items()},
        )
        subbed_type = type(self)(
            attributes,
        )
        if self._internal_name is not None:
            subbed_type.set_internal_name(self._internal_name)
        return subbed_type

    def constrain_and_bind_variables(
        self,
        context: TypeChecker,
        supertype: Type,
        rigid_variables: AbstractSet['Variable'],
        subtyping_assumptions: List[Tuple['Type', 'Type']],
    ) -> 'Substitutions':
        _logger.debug('{} <:? {}', self, supertype)
        # every object type is a subtype of object_type
        if (
            self._type_id == supertype._type_id
            or supertype._type_id == Type.the_object_type_id
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

        if not (self.kind <= supertype.kind):
            raise ConcatTypeError(
                format_subkinding_error(self, supertype),
                is_occurs_check_fail=False,
                rigid_variables=rigid_variables,
            )

        if isinstance(supertype, (StackEffect, PythonFunctionType)):
            sub = self.get_type_of_attribute(
                '__call__'
            ).constrain_and_bind_variables(
                context,
                supertype,
                rigid_variables,
                subtyping_assumptions,
            )
            sub.add_subtyping_provenance((self, supertype))
            return sub
        if isinstance(supertype, _PythonOverloadedType):
            sub = Substitutions()
            if supertype.overloads:
                sub = self.get_type_of_attribute(
                    '__call__'
                ).constrain_and_bind_variables(
                    context,
                    supertype,
                    rigid_variables,
                    subtyping_assumptions,
                )
            sub.add_subtyping_provenance((self, supertype))
            return sub
        if isinstance(supertype, _OptionalType):
            try:
                sub = self.constrain_and_bind_variables(
                    context,
                    context.none_type,
                    rigid_variables,
                    subtyping_assumptions + [(self, supertype)],
                )
                sub.add_subtyping_provenance((self, supertype))
                return sub
            except ConcatTypeError:
                sub = self.constrain_and_bind_variables(
                    context,
                    supertype.type_arguments[0],
                    rigid_variables,
                    subtyping_assumptions + [(self, supertype)],
                )
                sub.add_subtyping_provenance((self, supertype))
                return sub
        if isinstance(supertype, _NoReturnType):
            raise ConcatTypeError(
                format_subtyping_error(self, supertype),
                is_occurs_check_fail=None,
                rigid_variables=rigid_variables,
            )
        if isinstance(supertype, Fix):
            unrolled = supertype.unroll()
            sub = self.constrain_and_bind_variables(
                context,
                unrolled,
                rigid_variables,
                subtyping_assumptions + [(self, supertype)],
            )
            sub.add_subtyping_provenance((self, supertype))
            return sub
        # Don't forget that there's nominal subtyping too.
        if isinstance(supertype, NominalType):
            raise ConcatTypeError(
                f'{format_subtyping_error(self, supertype)}, {
                    format_not_a_nominal_type_error(self)
                }',
                is_occurs_check_fail=None,
                rigid_variables=rigid_variables,
            )
        if (
            isinstance(supertype, (TypeApplication, Projection))
            and supertype.is_redex()
            or isinstance(supertype, DelayedSubstitution)
        ):
            sub = self.constrain_and_bind_variables(
                context,
                supertype.force(),
                rigid_variables,
                subtyping_assumptions,
            )
            sub.add_subtyping_provenance((self, supertype))
            return sub
        if not isinstance(supertype, ObjectType):
            raise NotImplementedError(repr(supertype))

        # don't constrain the type arguments, constrain those based on
        # the attributes
        sub = Substitutions()
        for name in supertype._attributes:
            type = self.get_type_of_attribute(name)
            sub = sub(type).constrain_and_bind_variables(
                context,
                sub(supertype.get_type_of_attribute(name)),
                rigid_variables,
                subtyping_assumptions,
            )(sub)
        sub.add_subtyping_provenance((self, supertype))
        return sub

    def __repr__(self) -> str:
        return f'{type(self).__qualname__}(attributes={self._attributes!r})'

    def force_repr(self) -> str:
        attributes = _mapping_to_str(
            {a: t.force_repr() for a, t in self._attributes.items()}
        )
        return f'{type(self).__qualname__}(attributes={attributes})'

    def _free_type_variables(self) -> InsertionOrderedSet[Variable]:
        ftv = free_type_variables_of_mapping(self.attributes)
        # QUESTION: Include supertypes?
        return ftv

    def __str__(self) -> str:
        if self._internal_name is not None:
            return self._internal_name
        return f'ObjectType({_mapping_to_str(self._attributes)})'

    @property
    def attributes(self) -> Mapping[str, Type]:
        return self._attributes


class TypeTuple(Type):
    """Type-level tuples (products)."""

    def __init__(self, types: Sequence[Type]) -> None:
        super().__init__()
        self._types = types

    def constrain_and_bind_variables(
        self,
        context: TypeChecker,
        supertype,
        rigid_variables,
        subtyping_assumptions,
    ) -> Substitutions:
        if isinstance(supertype, DelayedSubstitution):
            supertype = supertype.force()
        if self._type_id == supertype._type_id or _contains_assumption(
            subtyping_assumptions, self, supertype
        ):
            return Substitutions()
        # NOTE: Don't raise normal errors. Tuple types shouldn't be
        # exposed to the user.
        # FIXME: Turns out the user can trigger this. :/
        assert self.kind <= supertype.kind, format_subkinding_error(
            self,
            supertype,
        )
        # TODO: Support Fix
        if not isinstance(supertype, TypeTuple):
            raise NotImplementedError(repr(supertype))
        sub = Substitutions()
        for subty, superty in zip(self._types, supertype._types):
            sub = sub(subty).constrain_and_bind_variables(
                context, sub(superty), rigid_variables, subtyping_assumptions
            )(sub)
        sub.add_subtyping_provenance((self, supertype))
        return sub

    def _free_type_variables(self) -> InsertionOrderedSet[Variable]:
        return functools.reduce(
            operator.or_,
            (t.free_type_variables() for t in self._types),
            InsertionOrderedSet([]),
        )

    def force_substitution(self, sub) -> TypeTuple:
        return TypeTuple([sub(t) for t in self._types])

    @property
    def attributes(self) -> NoReturn:
        raise TypeError(format_cannot_have_attributes_error(self))

    @property
    def kind(self) -> TupleKind:
        return TupleKind([t.kind for t in self._types])

    def project(self, n: int) -> Type:
        assert n < len(
            self._types
        ), format_type_tuple_index_out_of_range_error(self, n)
        return self._types[n]

    def __repr__(self) -> str:
        return f'TypeTuple({self._types!r})'

    def force_repr(self) -> str:
        return f'TypeTuple({
            _iterable_to_str(t.force_repr() for t in self._types)
        })'

    def __str__(self) -> str:
        return f'({','.join(str(t) for t in self._types)})'


class DelayedSubstitution(Type):
    def __init__(self, sub: Substitutions, ty: Type) -> None:
        super().__init__()
        self._sub: Substitutions
        self._ty: Type
        if isinstance(ty, DelayedSubstitution):
            sub = sub(ty._sub)
            ty = ty._ty
        self._sub = Substitutions(
            {v: t for v, t in sub.items() if v in ty.free_type_variables()}
        )
        self._ty = ty
        self._forced: Type | None = None

    def project(self, n: int) -> DelayedSubstitution:
        return DelayedSubstitution(self._sub, self._ty.project(n))

    def __getitem__(self, x: Any) -> Type:
        if self.kind <= SequenceKind:
            return self.force()[x]
        return DelayedSubstitution(self._sub, self._ty[x])

    def apply_is_redex(self) -> bool:
        return True

    def __len__(self) -> int:
        return len(self.force())

    def __bool__(self) -> bool:
        return True

    def instantiate(self) -> DelayedSubstitution:
        return DelayedSubstitution(self._sub, self._ty.instantiate())

    def __repr__(self) -> str:
        return f'DelayedSubstitution({self._sub!r}, {self._ty!r})'

    def force_repr(self) -> str:
        return self.force().force_repr()

    def __str__(self) -> str:
        return str(self.force())

    def _free_type_variables(self) -> InsertionOrderedSet[Variable]:
        return functools.reduce(
            operator.or_,
            (
                self._sub(v).free_type_variables()
                for v in self._ty.free_type_variables()
            ),
            InsertionOrderedSet([]),
        )

    @_sub_cache
    def apply_substitution(self, sub: Substitutions) -> Type:
        return DelayedSubstitution(sub(self._sub), self._ty)

    def force_substitution(self, sub: Substitutions) -> Type:
        return self.apply_substitution(sub)

    @property
    def attributes(self) -> Mapping[str, Type]:
        return self.force().attributes

    def constrain_and_bind_variables(
        self, context, supertype, rigid_variables, subtyping_assumptions
    ) -> Substitutions:
        if (
            self._type_id == supertype._type_id
            or _contains_assumption(subtyping_assumptions, self, supertype)
            or self.kind <= ItemKind
            and supertype._type_id == Type.the_object_type_id
        ):
            return Substitutions()
        if (
            isinstance(supertype, DelayedSubstitution)
            and self._sub == supertype._sub
        ):
            return self._ty.constrain_and_bind_variables(
                context, supertype._ty, rigid_variables, subtyping_assumptions
            )
        return self.force().constrain_and_bind_variables(
            context, supertype, rigid_variables, subtyping_assumptions
        )

    @property
    def kind(self) -> Kind:
        return self._ty.kind

    def force(self) -> Type:
        if not self._forced:
            self._forced = self._ty.force_substitution(self._sub)
            self._forced._type_id = self._type_id
            assert not isinstance(
                self._forced, DelayedSubstitution
            ), f'{self._ty!r}'
        return self._forced

    def __iter__(self) -> Iterator[DelayedSubstitution]:
        assert isinstance(self._ty, (StackEffect, TypeSequence))
        for component in self._ty:
            yield DelayedSubstitution(self._sub, component)

    @property
    def input(self) -> DelayedSubstitution:
        assert isinstance(self._ty, (StackEffect, PythonFunctionType))
        return DelayedSubstitution(self._sub, self._ty.input)

    @property
    def output(self) -> DelayedSubstitution:
        assert isinstance(self._ty, (StackEffect, PythonFunctionType))
        return DelayedSubstitution(self._sub, self._ty.output)

    @property
    def arguments(self) -> Sequence[Type]:
        assert isinstance(self.force(), VariableArgumentPack)
        return self.force().arguments


class VariableArgumentPack(Type):
    """List of types passed as an argument in a variable-length argument \
    position."""

    def __init__(self, types: Sequence[Type]) -> None:
        super().__init__()
        self._types = types

    def __str__(self) -> str:
        return f'variable-length arguments {', '.join(str(t) for t in self._types)}'

    def __repr__(self) -> str:
        return f'VariableArgumentPack({self._types!r})'

    def force_repr(self) -> str:
        return f'VariableArgumentPack({_iterable_to_str(t.force_repr() for t in self._types)})'

    @property
    def arguments(self) -> Sequence[Type]:
        return self._types

    @classmethod
    def collect_arguments(cls, args: Iterable[Type]) -> VariableArgumentPack:
        flattened_args: list[Type] = []
        for arg in args:
            if isinstance(arg, DelayedSubstitution):
                arg = arg.force()
            if isinstance(arg, VariableArgumentPack):
                flattened_args += arg._types
                continue
            flattened_args.append(arg)
        return VariableArgumentPack(flattened_args)

    def constrain_and_bind_variables(
        self,
        context: TypeChecker,
        supertype,
        rigid_variables,
        subtyping_assumptions,
    ) -> Substitutions:
        if self._type_id == supertype._type_id or _contains_assumption(
            subtyping_assumptions, self, supertype
        ):
            return Substitutions()
        if not (self.kind <= supertype.kind):
            raise ConcatTypeError(
                format_subkinding_error(self, supertype),
                is_occurs_check_fail=None,
                rigid_variables=rigid_variables,
            )
        if len(self._types) == 1 and isinstance(
            self._types[0].kind, VariableArgumentKind
        ):
            return self._types[0].constrain_and_bind_variables(
                context, supertype, rigid_variables, subtyping_assumptions
            )
        if (
            isinstance(supertype, Variable)
            and supertype not in rigid_variables
            # occurs check!
            and supertype not in self.free_type_variables()
        ):
            return Substitutions([(supertype, self)])
        if not isinstance(supertype, VariableArgumentPack):
            raise NotImplementedError
        sub = Substitutions()
        for subty, superty in zip(self._types, supertype._types):
            sub = sub(subty).constrain_and_bind_variables(
                context, sub(superty), rigid_variables, subtyping_assumptions
            )(sub)
        sub.add_subtyping_provenance((self, supertype))
        return sub

    def _free_type_variables(self) -> InsertionOrderedSet[Variable]:
        return functools.reduce(
            operator.or_,
            (t.free_type_variables() for t in self._types),
            InsertionOrderedSet([]),
        )

    def force_substitution(self, sub) -> VariableArgumentPack:
        return VariableArgumentPack.collect_arguments(
            [sub(t) for t in self._types]
        )

    @property
    def attributes(self) -> NoReturn:
        raise ConcatTypeError(
            format_cannot_have_attributes_error(self),
            is_occurs_check_fail=None,
            rigid_variables=None,
        )

    @property
    def kind(self) -> VariableArgumentKind:
        return VariableArgumentKind(
            functools.reduce(
                operator.or_,
                (self._underlying_kind(t.kind) for t in self._types),
                BottomKind,
            ),
        )

    @staticmethod
    def _underlying_kind(kind: Kind) -> Kind:
        if isinstance(kind, VariableArgumentKind):
            return kind._argument_kind
        return kind


# QUESTION: Should this exist, or should I use ObjectType?
class ClassType(ObjectType):
    """The representation of types of classes, like in "Design and Evaluation of Gradual Typing for Python" (Vitousek et al. 2014)."""

    def constrain_and_bind_variables(
        self,
        context: TypeChecker,
        supertype,
        rigid_variables,
        subtyping_assumptions,
    ) -> 'Substitutions':
        if isinstance(supertype, DelayedSubstitution):
            supertype = supertype.force()
        if (
            not supertype.has_attribute('__call__')
            or '__init__' not in self._attributes
        ):
            sub = super().constrain_and_bind_variables(
                context, supertype, rigid_variables, subtyping_assumptions
            )
            sub.add_subtyping_provenance((self, supertype))
            return sub
        init = self.get_type_of_attribute('__init__')
        # FIXME: Use constraint to allow more kinds of type rep
        while not isinstance(init, (StackEffect, PythonFunctionType)):
            init = init.get_type_of_attribute('__call__')
            if isinstance(init, DelayedSubstitution):
                init = init.force()
        bound_init = init.bind()
        sub = bound_init.constrain_and_bind_variables(
            context,
            supertype.get_type_of_attribute('__call__'),
            rigid_variables,
            subtyping_assumptions + [(self, supertype)],
        )
        sub.add_subtyping_provenance((self, supertype))
        return sub


class PythonFunctionType(IndividualType):
    def __init__(
        self,
        inputs: Type,
        output: Type,
    ) -> None:
        super().__init__()
        self._type_arguments: Sequence[Type] = [inputs, output]
        i, o = inputs, output
        if i.kind != SequenceKind:
            raise ConcatTypeError(
                f'{i} must be a sequence type, but has kind {i.kind}',
                is_occurs_check_fail=None,
                rigid_variables=None,
            )
        # HACK: Sequence variables are introduced by the type sequence AST nodes
        if isinstance(i, TypeSequence) and i and i[0].kind == SequenceKind:
            i = TypeSequence(i.as_sequence()[1:])
        _type_arguments = i, o
        if not (o.kind <= ItemKind):
            raise ConcatTypeError(
                f'{o} must be an item type, but has kind {o.kind}',
                is_occurs_check_fail=None,
                rigid_variables=None,
            )
        self._type_arguments = _type_arguments

    def _free_type_variables(self) -> InsertionOrderedSet[Variable]:
        ftv = self.input.free_type_variables()
        ftv |= self.output.free_type_variables()
        return ftv

    @property
    def kind(self) -> 'Kind':
        return IndividualKind

    def __repr__(self) -> str:
        return (
            f'PythonFunctionType(inputs={self.input!r}, '
            f'output={self.output!r})'
        )

    def force_repr(self) -> str:
        return (
            f'PythonFunctionType(inputs={self.input.force_repr()}, '
            f'output={self.output.force_repr()})'
        )

    def __str__(self) -> str:
        return f'py_function_type[{self.input}, {self.output}]'

    @property
    def attributes(self) -> Mapping[str, Type]:
        return {**super().attributes, '__call__': self}

    def force_substitution(self, sub: Substitutions) -> 'PythonFunctionType':
        inp = sub(self.input)
        out = sub(self.output)
        return PythonFunctionType(inputs=inp, output=out)

    @property
    def input(self) -> Type:
        return self._type_arguments[0]

    @property
    def output(self) -> Type:
        return self._type_arguments[1]

    def bind(self) -> 'PythonFunctionType':
        inputs = self.input[1:]
        output = self.output
        return PythonFunctionType(
            inputs=TypeSequence(inputs),
            output=output,
        )

    def constrain_and_bind_variables(
        self,
        context: TypeChecker,
        supertype: Type,
        rigid_variables: AbstractSet['Variable'],
        subtyping_assumptions: List[Tuple['Type', 'Type']],
    ) -> 'Substitutions':
        if isinstance(supertype, DelayedSubstitution):
            supertype = supertype.force()
        if self._type_id == supertype._type_id or _contains_assumption(
            subtyping_assumptions, self, supertype
        ):
            sub = Substitutions()
            sub.add_subtyping_provenance((self, supertype))
            return sub
        if not (self.kind <= supertype.kind):
            raise ConcatTypeError(
                format_subkinding_error(self, supertype),
                is_occurs_check_fail=None,
                rigid_variables=rigid_variables,
            )
        if supertype._type_id in (
            context.object_type._type_id,
            py_overloaded_type[()]._type_id,
        ):
            sub = Substitutions()
            sub.add_subtyping_provenance((self, supertype))
            return sub
        if (
            isinstance(supertype, Variable)
            and supertype.kind <= ItemKind
            and supertype not in rigid_variables
        ):
            if supertype in self.free_type_variables():
                raise ConcatTypeError(
                    format_occurs_error(supertype, self),
                    is_occurs_check_fail=True,
                    rigid_variables=rigid_variables,
                )
            sub = Substitutions([(supertype, self)])
            sub.add_subtyping_provenance((self, supertype))
            return sub
        if isinstance(supertype, _OptionalType):
            sub = self.constrain_and_bind_variables(
                context,
                supertype.type_arguments[0],
                rigid_variables,
                subtyping_assumptions,
            )
            sub.add_subtyping_provenance((self, supertype))
            return sub
        if isinstance(supertype, ObjectType):
            sub = Substitutions()
            for attr in supertype.attributes:
                self_attr_type = sub(self.get_type_of_attribute(attr))
                supertype_attr_type = sub(
                    supertype.get_type_of_attribute(attr)
                )
                sub = self_attr_type.constrain_and_bind_variables(
                    context,
                    supertype_attr_type,
                    rigid_variables,
                    subtyping_assumptions,
                )
            sub.add_subtyping_provenance((self, supertype))
            return sub
        if isinstance(supertype, PythonFunctionType):
            self_input_types = self.input
            supertype_input_types = supertype.input
            sub = supertype_input_types.constrain_and_bind_variables(
                context,
                self_input_types,
                rigid_variables,
                subtyping_assumptions,
            )
            sub = sub(self.output).constrain_and_bind_variables(
                context,
                sub(supertype.output),
                rigid_variables,
                subtyping_assumptions,
            )(sub)
            sub.add_subtyping_provenance((self, supertype))
            return sub
        raise ConcatTypeError(
            f'{self} is not a subtype of {supertype}',
            is_occurs_check_fail=False,
            rigid_variables=rigid_variables,
        )


class _PythonOverloadedType(IndividualType):
    def __init__(
        self, overloads: VariableArgumentPack | DelayedSubstitution
    ) -> None:
        super().__init__()
        _fixed_overloads: List[Type] = []
        self._overloads: VariableArgumentPack
        for overload in overloads.arguments:
            if isinstance(overload, DelayedSubstitution):
                overload = overload.force()
            if isinstance(overload, Variable):
                # Variable should already be kind-checked.
                _fixed_overloads.append(overload)
                continue
            if isinstance(overload, _PythonOverloadedType):
                _fixed_overloads += overload._overloads.arguments
                continue
            if not isinstance(overload, PythonFunctionType):
                raise ConcatTypeError(
                    format_not_allowed_as_overload_error(overload),
                    is_occurs_check_fail=None,
                    rigid_variables=None,
                )
            i, o = overload.input, overload.output
            # HACK: Sequence variables are introduced by the type sequence AST nodes
            if isinstance(i, TypeSequence) and i and i[0].kind == SequenceKind:
                i = TypeSequence(i.as_sequence()[1:])
            _fixed_overloads.append(PythonFunctionType(i, o))
        self._overloads = VariableArgumentPack(_fixed_overloads)

    def __getitem__(self, args: Sequence[Type]) -> NoReturn:
        raise ConcatTypeError(
            format_not_generic_type_error(self),
            is_occurs_check_fail=None,
            rigid_variables=None,
        )

    @property
    def attributes(self) -> Mapping[str, 'Type']:
        return {'__call__': self}

    def _free_type_variables(self) -> InsertionOrderedSet['Variable']:
        return self._overloads.free_type_variables()

    def bind(self) -> _PythonOverloadedType:
        return _PythonOverloadedType(
            VariableArgumentPack(
                [
                    f.bind()
                    for f in self._overloads.arguments
                    if isinstance(f, PythonFunctionType)
                ]
            )
        )

    def force_substitution(
        self, sub: Substitutions
    ) -> '_PythonOverloadedType':
        return _PythonOverloadedType(sub(self._overloads))

    def constrain_and_bind_variables(
        self,
        context: TypeChecker,
        supertype: 'Type',
        rigid_variables: AbstractSet['Variable'],
        subtyping_assumptions: List[Tuple['Type', 'Type']],
    ) -> 'Substitutions':
        if isinstance(supertype, DelayedSubstitution):
            supertype = supertype.force()
        if (
            self is supertype
            or _contains_assumption(subtyping_assumptions, self, supertype)
            or supertype == context.object_type
        ):
            sub = Substitutions()
            sub.add_subtyping_provenance((self, supertype))
            return sub
        if not (self.kind <= supertype.kind):
            raise ConcatTypeError(
                format_subkinding_error(self, supertype),
                is_occurs_check_fail=None,
                rigid_variables=rigid_variables,
            )
        if (
            isinstance(supertype, ItemVariable)
            and supertype not in rigid_variables
        ):
            sub = Substitutions([(supertype, self)])
            sub.add_subtyping_provenance((self, supertype))
            return sub
        if isinstance(supertype, _OptionalType):
            sub = self.constrain_and_bind_variables(
                context,
                supertype.type_arguments[0],
                rigid_variables,
                subtyping_assumptions,
            )
            sub.add_subtyping_provenance((self, supertype))
            return sub
        if isinstance(supertype, ObjectType):
            sub = Substitutions()
            for attr in supertype.attributes:
                self_attr_type = sub(self.get_type_of_attribute(attr))
                supertype_attr_type = sub(
                    supertype.get_type_of_attribute(attr)
                )
                sub = self_attr_type.constrain_and_bind_variables(
                    context,
                    supertype_attr_type,
                    rigid_variables,
                    subtyping_assumptions,
                )
            sub.add_subtyping_provenance((self, supertype))
            return sub
        if isinstance(supertype, PythonFunctionType):
            if (
                self._overloads.arguments
                and isinstance(self._overloads.arguments[0], Variable)
                and self._overloads.arguments[0].kind <= SequenceKind
            ):
                if self._overloads.arguments[0] in rigid_variables:
                    raise ConcatTypeError(
                        format_rigid_variable_error(
                            self._overloads.arguments[0], supertype
                        ),
                        is_occurs_check_fail=False,
                        rigid_variables=rigid_variables,
                    )
                sub = Substitutions(
                    [(self._overloads.arguments[0], TypeSequence([supertype]))]
                )
                sub.add_subtyping_provenance((self, supertype))
                return sub

            # Support overloading the subtype.
            exceptions = []
            for overload in self._overloads.arguments:
                if isinstance(overload, Variable) and isinstance(
                    overload.kind, VariableArgumentKind
                ):
                    sub = overload.constrain_and_bind_variables(
                        context,
                        VariableArgumentPack([supertype]),
                        rigid_variables,
                        subtyping_assumptions,
                    )
                    sub.add_subtyping_provenance((self, supertype))
                    return sub
                subtyping_assumptions_copy = subtyping_assumptions[:]
                try:
                    sub = overload.constrain_and_bind_variables(
                        context,
                        supertype,
                        rigid_variables,
                        subtyping_assumptions,
                    )
                    sub.add_subtyping_provenance((self, supertype))
                    return sub
                except ConcatTypeError as e:
                    exceptions.append(e)
                finally:
                    subtyping_assumptions[:] = subtyping_assumptions_copy
            raise ConcatTypeError(
                f'no overload of {self} is a subtype of {supertype}',
                any(e.is_occurs_check_fail for e in exceptions),
                rigid_variables,
            ) from ExceptionGroup(
                f'{self} is not compatible with {supertype}', exceptions
            )
        if isinstance(supertype, _PythonOverloadedType):
            # TODO: unsure what to do here
            raise NotImplementedError
        raise ConcatTypeError(
            f'{self} is not a subtype of {supertype}',
            is_occurs_check_fail=None,
            rigid_variables=rigid_variables,
        )

    def __str__(self) -> str:
        return f'py_overloaded[{', '.join(str(t) for t in self._overloads.arguments)}]'

    def __repr__(self) -> str:
        return f'_PythonOverloadedType({self._overloads!r})'

    def force_repr(self) -> str:
        return f'_PythonOverloadedType({self._overloads.force_repr()})'

    @property
    def overloads(self) -> Sequence[Type]:
        return self._overloads.arguments


class _NoReturnType(IndividualType):
    def constrain_and_bind_variables(
        self,
        context: TypeChecker,
        supertype,
        rigid_variables,
        subtyping_assumptions,
    ) -> 'Substitutions':
        return Substitutions()

    @_sub_cache
    def apply_substitution(self, sub: Substitutions) -> '_NoReturnType':
        return self

    def force_substitution(self, sub: Substitutions) -> _NoReturnType:
        return self.apply_substitution(sub)

    def __repr__(self) -> str:
        return '_NoReturnType()'

    def force_repr(self) -> str:
        return repr(self)

    def _free_type_variables(self) -> InsertionOrderedSet['Variable']:
        return InsertionOrderedSet([])


class _OptionalType(IndividualType):
    def __init__(self, type_argument: Type) -> None:
        super().__init__()
        if not (type_argument.kind <= ItemKind):
            raise ConcatTypeError(
                format_must_be_item_type_error(type_argument),
                is_occurs_check_fail=None,
                rigid_variables=None,
            )
        while isinstance(type_argument, _OptionalType):
            type_argument = type_argument._type_argument
        self._type_argument: Type = type_argument

    def __repr__(self) -> str:
        return f'_OptionalType({self._type_argument!r})'

    def force_repr(self) -> str:
        return f'_OptionalType({self._type_argument.force_repr()})'

    def __str__(self) -> str:
        return f'optional_type[{self._type_argument}]'

    def _free_type_variables(self) -> InsertionOrderedSet[Variable]:
        return self._type_argument.free_type_variables()

    def __eq__(self, other: object) -> bool:
        if isinstance(other, _OptionalType):
            return self._type_argument == other._type_argument
        return super().__eq__(other)

    def constrain_and_bind_variables(
        self,
        context: TypeChecker,
        supertype,
        rigid_variables,
        subtyping_assumptions,
    ) -> 'Substitutions':
        if (
            self is supertype
            or _contains_assumption(subtyping_assumptions, self, supertype)
            or supertype is context.object_type
        ):
            return Substitutions()
        # A special case for better resuls (I think)
        if isinstance(supertype, _OptionalType):
            return self._type_argument.constrain_and_bind_variables(
                context,
                supertype._type_argument,
                rigid_variables,
                subtyping_assumptions,
            )
        if not (self.kind <= supertype.kind):
            raise ConcatTypeError(
                format_subkinding_error(self, supertype),
                is_occurs_check_fail=None,
                rigid_variables=rigid_variables,
            )
        # FIXME: optional[none] should simplify to none
        if (
            self._type_argument is context.none_type
            and supertype is context.none_type
        ):
            return Substitutions()

        if isinstance(supertype, Fix):
            return self.constrain_and_bind_variables(
                context,
                supertype.unroll(),
                rigid_variables,
                subtyping_assumptions + [(self, supertype)],
            )

        sub = context.none_type.constrain_and_bind_variables(
            context, supertype, rigid_variables, subtyping_assumptions
        )
        sub = sub(self._type_argument).constrain_and_bind_variables(
            context, sub(supertype), rigid_variables, subtyping_assumptions
        )
        return sub

    def force_substitution(self, sub: Substitutions) -> '_OptionalType':
        return _OptionalType(sub(self._type_argument))

    @property
    def type_arguments(self) -> Sequence[Type]:
        return [self._type_argument]


class Kind(abc.ABC):
    @abc.abstractmethod
    def __or__(self, other: Kind) -> Kind:
        pass

    @abc.abstractmethod
    def __and__(self, other: Kind) -> Kind:
        pass

    @abc.abstractmethod
    def __eq__(self, other: object) -> bool:
        pass

    def __lt__(self, other: Kind) -> bool:
        return self <= other and self != other

    def __le__(self, other: Kind) -> bool:
        return self | other == other

    def __ge__(self, other: Kind) -> bool:
        return other <= self

    @abc.abstractmethod
    def __str__(self) -> str:
        pass


class VariableArgumentKind(Kind):
    """The kind of type-level variable arguments."""

    def __init__(self, argument_kind: Kind) -> None:
        self._argument_kind = argument_kind

    @property
    def argument_kind(self) -> Kind:
        return self._argument_kind

    def __eq__(self, other: object) -> bool:
        return (
            isinstance(other, VariableArgumentKind)
            and self._argument_kind == other._argument_kind
        )

    def __or__(self, other: Kind) -> Kind:
        if other is BottomKind:
            return self
        if isinstance(other, VariableArgumentKind):
            return VariableArgumentKind(
                self._argument_kind | other._argument_kind
            )
        return TopKind

    def __and__(self, other: Kind) -> Kind:
        if other is TopKind:
            return self
        if isinstance(other, VariableArgumentKind):
            return VariableArgumentKind(
                self._argument_kind & other._argument_kind
            )
        return BottomKind

    def __str__(self) -> str:
        return f'VariableArgument[{self._argument_kind}]'


class TupleKind(Kind):
    def __init__(self, kinds: Sequence[Kind]) -> None:
        self._kinds = [*kinds]

    def __eq__(self, other) -> bool:
        if not isinstance(other, Kind):
            return NotImplemented
        return isinstance(other, TupleKind) and self._kinds == other._kinds

    def __or__(self, other: Kind) -> Kind:
        if other is BottomKind:
            return self
        if isinstance(other, TupleKind) and len(self._kinds) == len(
            other._kinds
        ):
            return TupleKind(
                [a | b for a, b in zip(self._kinds, other._kinds)]
            )
        return TopKind

    def __and__(self, other: Kind) -> Kind:
        if other is TopKind:
            return self
        if isinstance(other, TupleKind) and len(self._kinds) == len(
            other._kinds
        ):
            return TupleKind(
                [a & b for a, b in zip(self._kinds, other._kinds)]
            )
        return BottomKind

    def __str__(self) -> str:
        return f'Tuple[{', '.join(str(k) for k in self._kinds)}]'

    def __repr__(self) -> str:
        return f'TupleKind({self._kinds!r})'

    @property
    def element_kinds(self) -> Sequence[Kind]:
        return self._kinds


class _ItemKind(Kind):
    __instance: Optional['_ItemKind'] = None

    def __new__(cls) -> '_ItemKind':
        if cls.__instance is None:
            cls.__instance = super().__new__(cls)
        return cls.__instance

    def __eq__(self, other: object) -> bool:
        return self is other

    def __or__(self, other: Kind) -> Kind:
        if (
            other is BottomKind
            or other is IndividualKind
            or other is self
            or isinstance(other, GenericTypeKind)
        ):
            return self
        return TopKind

    def __and__(self, other: Kind) -> Kind:
        if other is TopKind or other is self:
            return self
        if other is IndividualKind or isinstance(other, GenericTypeKind):
            return other
        return BottomKind

    def __str__(self) -> str:
        return 'Item'


ItemKind = _ItemKind()


class _TopKind(Kind):
    __instance: Optional[_TopKind] = None

    def __new__(cls) -> _TopKind:
        if cls.__instance is None:
            cls.__instance = super().__new__(cls)
        return cls.__instance

    def __eq__(self, other: object) -> bool:
        return self is other

    def __or__(self, other: Kind) -> Kind:
        return self

    def __and__(self, other: Kind) -> Kind:
        return other

    def __str__(self) -> str:
        return 'Top'


TopKind = _TopKind()


class _BottomKind(Kind):
    __instance: Optional[_BottomKind] = None

    def __new__(cls) -> _BottomKind:
        if cls.__instance is None:
            cls.__instance = super().__new__(cls)
        return cls.__instance

    def __eq__(self, other: object) -> bool:
        return self is other

    def __or__(self, other: Kind) -> Kind:
        return other

    def __and__(self, other: Kind) -> Kind:
        return self

    def __str__(self) -> str:
        return 'Bottom'


BottomKind = _BottomKind()


class _IndividualKind(Kind):
    __instance: Optional['_IndividualKind'] = None

    def __new__(cls) -> '_IndividualKind':
        if cls.__instance is None:
            cls.__instance = super().__new__(cls)
        return cls.__instance

    def __eq__(self, other: object) -> bool:
        return self is other

    def __or__(self, other: Kind) -> Kind:
        if other is self or other is BottomKind:
            return self
        if isinstance(other, GenericTypeKind) or other is ItemKind:
            return ItemKind
        return TopKind

    def __and__(self, other: Kind) -> Kind:
        if other is self or other is ItemKind or other is TopKind:
            return self
        return BottomKind

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

    def __or__(self, other: Kind) -> Kind:
        if other is BottomKind or other is self:
            return self
        return TopKind

    def __and__(self, other: Kind) -> Kind:
        if other is TopKind or other is self:
            return self
        return BottomKind

    def __str__(self) -> str:
        return 'Sequence'


SequenceKind = _SequenceKind()


class GenericTypeKind(Kind):
    def __init__(
        self, parameter_kinds: Sequence[Kind], result_kind: Kind
    ) -> None:
        if not parameter_kinds:
            raise ConcatTypeError(
                'Generic type kinds cannot have empty parameters',
                is_occurs_check_fail=None,
                rigid_variables=None,
            )
        self.parameter_kinds = parameter_kinds
        self.result_kind = result_kind

    def __eq__(self, other: object) -> bool:
        return (
            isinstance(other, GenericTypeKind)
            and list(self.parameter_kinds) == list(other.parameter_kinds)
            and self.result_kind == other.result_kind
        )

    def __or__(self, other: Kind) -> Kind:
        if other is BottomKind:
            return self
        if isinstance(other, GenericTypeKind):
            if len(self.parameter_kinds) == len(other.parameter_kinds):
                return GenericTypeKind(
                    [
                        a & b
                        for a, b in zip(
                            self.parameter_kinds, other.parameter_kinds
                        )
                    ],
                    self.result_kind | other.result_kind,
                )
            return ItemKind
        if other is IndividualKind or other is ItemKind:
            return ItemKind
        return TopKind

    def __and__(self, other: Kind) -> Kind:
        if other is TopKind or other is ItemKind:
            return self
        if isinstance(other, GenericTypeKind):
            if len(self.parameter_kinds) == len(other.parameter_kinds):
                return GenericTypeKind(
                    [
                        a | b
                        for a, b in zip(
                            self.parameter_kinds, other.parameter_kinds
                        )
                    ],
                    self.result_kind & other.result_kind,
                )
            return BottomKind
        return BottomKind

    def __str__(self) -> str:
        return f'Generic[{", ".join(map(str, self.parameter_kinds))}, {self.result_kind}]'

    def __repr__(self) -> str:
        return (
            f'GenericTypeKind({self.parameter_kinds!r}, {self.result_kind!r})'
        )


class Fix(Type):
    def __init__(self, var: Variable, body: Type) -> None:
        super().__init__()
        assert var.kind >= body.kind, f'{var.kind!r}, {body.kind!r}'
        self._var = var
        self._body = body
        self._unrolled_ty: Optional[Type] = None
        self._cache: Dict[int, Type] = {}

    def __repr__(self) -> str:
        return f'Fix({self._var!r}, {self._body!r})'

    def force_repr(self) -> str:
        return f'Fix({self._var!r}, {self._body.force_repr()})'

    def __str__(self) -> str:
        if self._internal_name is not None:
            return self._internal_name
        return f'Fix({self._var}, {self._body})'

    def _apply(self, t: Type) -> Type:
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
            # Do not make the type ids equal so that subtyping assumptions are
            # useful
        return self._unrolled_ty

    def _free_type_variables(self) -> InsertionOrderedSet[Variable]:
        return self._body.free_type_variables() - {self._var}

    def force_substitution(self, sub: 'Substitutions') -> Type:
        sub = Substitutions(
            {v: t for v, t in sub.items() if v is not self._var}
        )

        return Fix(self._var, sub(self._body))

    @property
    def attributes(self) -> Mapping[str, Type]:
        return self.unroll().attributes

    def constrain_and_bind_variables(
        self,
        context: TypeChecker,
        supertype,
        rigid_variables,
        subtyping_assumptions,
    ) -> 'Substitutions':
        _logger.debug('{} <:? {}', self, supertype)
        if isinstance(supertype, DelayedSubstitution):
            supertype = supertype.force()
        if (
            supertype._type_id == context.object_type._type_id
            or _contains_assumption(subtyping_assumptions, self, supertype)
        ):
            sub = Substitutions()
            sub.add_subtyping_provenance((self, supertype))
            return sub

        if isinstance(supertype, Fix):
            unrolled = supertype.unroll()
            sub = self.unroll().constrain_and_bind_variables(
                context,
                unrolled,
                rigid_variables,
                subtyping_assumptions + [(self, supertype)],
            )
            sub.add_subtyping_provenance((self, supertype))
            return sub

        sub = self.unroll().constrain_and_bind_variables(
            context,
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
        if isinstance(self._body, NominalType):
            return TypeApplication(self, args)
        return self.unroll()[args]

    def apply_is_redex(self) -> bool:
        return isinstance(self._body, NominalType)

    def force_apply(self, args: Any) -> Any:
        return self.unroll()[args]

    def project_is_redex(self) -> bool:
        return True

    def force_project(self, i: int) -> Type:
        return self.unroll().project(i)

    @property
    def brand(self) -> Brand:
        return self._body.brand


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


_overloads_var = BoundVariable(VariableArgumentKind(IndividualKind))
py_overloaded_type = GenericType(
    [_overloads_var],
    _PythonOverloadedType(VariableArgumentPack([_overloads_var])),
)
_x = BoundVariable(kind=IndividualKind)

float_type = NominalType(Brand('float', IndividualKind, []), ObjectType({}))
no_return_type = _NoReturnType()

_arg_type_var = SequenceVariable()
_return_type_var = ItemVariable(ItemKind)
py_function_type = GenericType(
    [_arg_type_var, _return_type_var],
    PythonFunctionType(inputs=_arg_type_var, output=_return_type_var),
)
py_function_type.set_internal_name('py_function_type')

_invert_result_var = ItemVariable(ItemKind)
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
