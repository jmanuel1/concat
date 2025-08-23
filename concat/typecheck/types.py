from __future__ import annotations

import abc
import functools
import logging
import operator
from collections import defaultdict
from collections.abc import Callable
from typing import (
    TYPE_CHECKING,
    AbstractSet,
    Any,
    Concatenate,
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
    format_expected_seq_kinded_variable_error,
    format_generic_type_attributes_error,
    format_item_type_expected_in_type_sequence_error,
    format_must_be_item_type_error,
    format_not_a_nominal_type_error,
    format_not_a_sequence_type_error,
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
    f: Callable[[T, TypeChecker, Substitutions], R],
) -> Callable[[T, TypeChecker, Substitutions], T | R]:
    _sub_cache = dict[tuple[int, int], T | R]()

    def apply_substitution(
        self: T, context: TypeChecker, sub: Substitutions
    ) -> T | R:
        if (self._type_id, sub.id) not in _sub_cache:
            if not (set(sub) & self.free_type_variables(context)):
                _sub_cache[self._type_id, sub.id] = self
            else:
                _sub_cache[self._type_id, sub.id] = f(self, context, sub)
        return _sub_cache[self._type_id, sub.id]

    return apply_substitution


type _ConstrainFn[T] = Callable[
    [T, TypeChecker, Type, AbstractSet[Variable], list[tuple[Type, Type]]],
    Substitutions,
]


def _constrain_on_whnf[T: Type](f: _ConstrainFn[T]) -> _ConstrainFn[T]:
    def constrain_and_bind_variables(
        self,
        context: TypeChecker,
        supertype: Type,
        rigid_variables: AbstractSet['Variable'],
        subtyping_assumptions: List[Tuple['Type', 'Type']],
    ) -> 'Substitutions':
        forced = self.force(context)
        if forced:
            return forced.constrain_and_bind_variables(
                context,
                supertype.force(context) or supertype,
                rigid_variables,
                subtyping_assumptions,
            )
        return f(
            self,
            context,
            supertype.force(context) or supertype,
            rigid_variables,
            subtyping_assumptions,
        )

    return constrain_and_bind_variables


def _whnf_self[T: Type, **K, R](
    f: Callable[Concatenate[T, TypeChecker, K], R],
) -> Callable[Concatenate[T, TypeChecker, K], R]:
    def g(
        self: T, context: TypeChecker, *args: K.args, **kwargs: K.kwargs
    ) -> R:
        forced = self.force(context)
        if forced:
            return getattr(forced, f.__name__)(context, *args, **kwargs)
        return f(self, context, *args, **kwargs)

    return g


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
        ftv = self.free_type_variables(context) | other.free_type_variables(
            context
        )
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

    def get_type_of_attribute(self, context: TypeChecker, name: str) -> 'Type':
        attributes = self.attributes(context)
        if name not in attributes:
            raise ConcatAttributeError(self, name)
        return attributes[name]

    def has_attribute(self, context: TypeChecker, name: str) -> bool:
        try:
            self.get_type_of_attribute(context, name)
            return True
        except ConcatAttributeError:
            return False

    @abc.abstractmethod
    def attributes(self, context: TypeChecker) -> Mapping[str, 'Type']:
        return {}

    @abc.abstractmethod
    def _free_type_variables(
        self, context: TypeChecker
    ) -> InsertionOrderedSet['Variable']:
        pass

    def free_type_variables(
        self, context: TypeChecker
    ) -> InsertionOrderedSet['Variable']:
        if self._free_type_variables_cached is None:
            # Break circular references. Recursing into the same type won't add
            # new FTVs, so we can pretend there are none we finish finding the
            # others.
            self._free_type_variables_cached = InsertionOrderedSet([])
            self._free_type_variables_cached = self._free_type_variables(
                context
            )
        return self._free_type_variables_cached

    @_sub_cache
    def apply_substitution(
        self, context: TypeChecker, sub: Substitutions
    ) -> 'Type':
        return DelayedSubstitution(context, sub, self)

    @abc.abstractmethod
    def force_substitution(
        self, context: TypeChecker, _: Substitutions
    ) -> 'Type':
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

    def instantiate(self, context: TypeChecker) -> 'Type':
        return self

    @abc.abstractproperty
    def kind(self) -> 'Kind':
        pass

    def set_internal_name(self, name: str) -> None:
        self._internal_name = name

    def to_user_string(self, context: TypeChecker) -> str:
        if self._internal_name is not None:
            return self._internal_name
        forced = self.force(context)
        if forced:
            return forced.to_user_string(context)
        return super().__str__()

    def to_string_for_stack_effect(self, context: TypeChecker) -> str:
        return self.to_user_string(context)

    @abc.abstractmethod
    def force(self, context: TypeChecker) -> Type | None:
        """Reduce this type representation to a weak head normal form.

        If it is already in weak head normal form, return None. Reduction is
        performed purely syntactically: in particular, subtyping is not
        considered where it requires checking constraints.
        """

    @abc.abstractmethod
    def force_repr(self, context: TypeChecker) -> str:
        pass

    def apply(self, context: TypeChecker, _: TypeArguments) -> Type:
        _logger.debug('tried to treat {} as generic', self)
        raise ConcatTypeError(
            format_not_generic_type_error(self),
            is_occurs_check_fail=None,
            rigid_variables=None,
        )

    def index(self, context: TypeChecker, i: int | slice) -> Type:
        raise ConcatTypeError(
            format_not_a_sequence_type_error(self),
            is_occurs_check_fail=None,
            rigid_variables=None,
        )

    def apply_is_redex(_) -> bool:
        return False

    def force_apply(self, context: TypeChecker, args: Any) -> Type:
        return self.apply(context, args)

    def project(self, context: TypeChecker, i: int) -> Type:
        return Projection(self, i)

    def project_is_redex(_) -> bool:
        return False

    def force_project(self, i: int) -> Type:
        return Projection(self, i)

    def brand(self, context: TypeChecker) -> Brand:
        raise ConcatTypeError(
            format_not_a_nominal_type_error(self),
            is_occurs_check_fail=None,
            rigid_variables=None,
        )

    def length(self, context: TypeChecker) -> int:
        raise ConcatTypeError(
            format_not_a_sequence_type_error(self),
            is_occurs_check_fail=False,
            rigid_variables=None,
        )


class IndividualType(Type):
    @property
    def kind(self) -> 'Kind':
        return IndividualKind


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

    def force_substitution(
        self, context: TypeChecker, sub: 'Substitutions'
    ) -> Type:
        forced = self._head.force_substitution(context, sub).apply(
            context, [t.apply_substitution(context, sub) for t in self._args]
        )
        return forced.force(context) or forced

    @_constrain_on_whnf
    def constrain_and_bind_variables(
        self,
        context: TypeChecker,
        supertype,
        rigid_variables,
        subtyping_assumptions,
    ) -> 'Substitutions':
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
            if supertype in self.free_type_variables(context):
                raise ConcatTypeError(
                    format_occurs_error(supertype, self),
                    is_occurs_check_fail=True,
                    rigid_variables=rigid_variables,
                )
            return Substitutions([(supertype, self)])
        raise ConcatTypeError(
            f'Cannot deduce that {self} is a subtype of {supertype} here',
            is_occurs_check_fail=False,
            rigid_variables=rigid_variables,
        )

    def is_redex(self) -> bool:
        return self._head.apply_is_redex()

    def force(self, context: TypeChecker) -> Type | None:
        if self.is_redex():
            if not self._forced:
                self._forced = self._head.force_apply(context, self._args)
            return self._forced.force(context) or self._forced
        return None

    def __str__(self) -> str:
        if self._internal_name is not None:
            return self._internal_name
        return f'{self._head}{_iterable_to_str(self._args)}'

    def __repr__(self) -> str:
        return f'TypeApplication({self._head!r}, {self._args!r})'

    @_whnf_self
    def force_repr(self, context: TypeChecker) -> str:
        return f'TypeApplication({self._head.force_repr(context)}, {[a.force_repr(context) for a in self._args]})'

    def _free_type_variables(
        self, context: TypeChecker
    ) -> InsertionOrderedSet['Variable']:
        ftv = self._head.free_type_variables(context)
        for arg in self._args:
            ftv |= arg.free_type_variables(context)
        return ftv

    def brand(self, context: TypeChecker) -> Brand:
        return self._head.brand(context)


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

    def _free_type_variables(
        self, context: TypeChecker
    ) -> InsertionOrderedSet[Variable]:
        return (self.force(context) or self._head).free_type_variables(context)

    def force_substitution(
        self, context: TypeChecker, sub: Substitutions
    ) -> Type:
        return self._head.force_substitution(context, sub).project(
            context, self._index
        )

    def attributes(self, context: TypeChecker) -> Mapping[str, Type]:
        forced = self.force(context)
        if forced:
            return forced.attributes(context)
        raise ConcatTypeError(
            format_attributes_unknown_error(self),
            is_occurs_check_fail=None,
            rigid_variables=None,
        )

    @_constrain_on_whnf
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
        raise ConcatTypeError(
            format_subtyping_error(self, supertype),
            is_occurs_check_fail=None,
            rigid_variables=rigid_variables,
        )

    @property
    def kind(self) -> Kind:
        return self._kind

    @_whnf_self
    def apply(self, context: TypeChecker, x: Any) -> Any:
        if self._kind <= SequenceKind:
            raise ConcatTypeError(
                format_unknown_sequence_type(self),
                is_occurs_check_fail=None,
                rigid_variables=None,
            )
        return TypeApplication(self, x)

    def apply_is_redex(self) -> bool:
        return True

    @_whnf_self
    def force_apply(self, context: TypeChecker, args: TypeArguments) -> Type:
        return self.apply(context, args)

    def is_redex(self) -> bool:
        return self._head.project_is_redex()

    def force(self, context: TypeChecker) -> Type | None:
        if self.is_redex():
            if not self._forced:
                self._forced = self._head.force_project(self._index)
                self._forced = self._forced.force(context) or self._forced
            return self._forced
        return None

    @_whnf_self
    def brand(self, context: TypeChecker) -> Brand:
        return (self.force(context) or cast(Type, super())).brand(context)

    def __repr__(self) -> str:
        return f'Projection({self._head!r}, {self._index!r})'

    @_whnf_self
    def force_repr(self, context: TypeChecker) -> str:
        return f'Projection({self._head.force_repr(context)}, {self._index!r})'

    @_whnf_self
    def to_user_string(self, context: TypeChecker) -> str:
        return f'{self._head}.{self._index}'


class Variable(Type, abc.ABC):
    """Objects that represent type variables.

    Every type variable object is assumed to be unique. Thus, fresh type
    variables can be made simply by creating new objects. They can also be
    compared by identity."""

    @_sub_cache
    def apply_substitution(
        self, context: TypeChecker, sub: Substitutions
    ) -> Type:
        if self in sub:
            result = sub[self]
            return result
        return self

    def force(self, context: TypeChecker) -> None:
        pass

    def force_substitution(
        self, context: TypeChecker, sub: Substitutions
    ) -> Type:
        result = self.apply_substitution(context, sub)
        return result.force(context) or result

    def _free_type_variables(
        self, context: TypeChecker
    ) -> InsertionOrderedSet['Variable']:
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

    def to_user_string(self, context: TypeChecker) -> str:
        return f't_{id(self)}'

    def force_repr(self, context: TypeChecker) -> str:
        return repr(self)

    def apply(self, context: TypeChecker, args: 'TypeArguments') -> Type:
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

    def to_user_string(self, context: TypeChecker) -> str:
        return f't_{id(self)} : {self._kind}'

    def to_string_for_stack_effect(self, context: TypeChecker) -> str:
        return f'({self.to_user_string(context)})'

    def attributes(self, context: TypeChecker) -> Mapping[str, Type]:
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

    @_constrain_on_whnf
    def constrain_and_bind_variables(
        self,
        context: TypeChecker,
        supertype: Type,
        rigid_variables: AbstractSet['Variable'],
        subtyping_assumptions: List[Tuple['Type', 'Type']],
    ) -> 'Substitutions':
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

    def to_user_string(self, context: TypeChecker) -> str:
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

    def to_user_string(self, context: TypeChecker) -> str:
        return '*t_{}'.format(id(self))

    def __repr__(self) -> str:
        return f'<sequence variable {id(self)}>'

    @_constrain_on_whnf
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
        if self is not supertype and self in supertype.free_type_variables(
            context
        ):
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

    def to_user_string(self, context: TypeChecker) -> str:
        if self._internal_name is not None:
            return self._internal_name
        if self.is_variadic:
            params = self._type_parameters[0].to_user_string(context) + '...'
        else:
            params = ' '.join(
                map(lambda p: p.to_user_string(context), self._type_parameters)
            )

        return f'forall {params}. {self._body}'

    def __repr__(self) -> str:
        return f'GenericType({self._type_parameters!r}, {self._body!r})'

    def force(self, context: TypeChecker) -> None:
        pass

    def force_repr(self, context: TypeChecker) -> str:
        return f'GenericType({_iterable_to_str(t.force_repr(context) for t in self._type_parameters)}, {self._body.force_repr(context)})'

    def apply(
        self, context: TypeChecker, type_arguments: 'TypeArguments'
    ) -> 'Type':
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
        instance = self._body.apply_substitution(context, sub)
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

    def instantiate(self, context: TypeChecker) -> Type:
        fresh_vars: Sequence[Variable] = [
            var.freshen() for var in self._type_parameters
        ]
        return self.apply(context, fresh_vars)

    @_constrain_on_whnf
    def constrain_and_bind_variables(
        self,
        context: TypeChecker,
        supertype: 'Type',
        rigid_variables: AbstractSet['Variable'],
        subtyping_assumptions: List[Tuple['Type', 'Type']],
    ) -> 'Substitutions':
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
                return self.apply(
                    context, fresh_args
                ).constrain_and_bind_variables(
                    context,
                    supertype.apply(context, fresh_args),
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
                inst = GenericType(
                    parameters_left,
                    self._body.apply_substitution(context, sub),
                )
            else:
                inst = self._body.apply_substitution(context, sub)
            return inst.constrain_and_bind_variables(
                context, supertype, rigid_variables, subtyping_assumptions
            )
        # supertype is a GenericType
        if any(
            map(
                lambda t: t in self.free_type_variables(context),
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
        return self.instantiate(context).constrain_and_bind_variables(
            context,
            supertype._body,
            rigid_variables | set(supertype._type_parameters),
            subtyping_assumptions,
        )

    def force_substitution(
        self, context: TypeChecker, sub: 'Substitutions'
    ) -> 'GenericType':
        sub = Substitutions(
            {
                var: ty
                for var, ty in sub.items()
                if var not in self._type_parameters
            }
        )
        ty = GenericType(
            self._type_parameters,
            self._body.apply_substitution(context, sub),
        )
        return ty

    @property
    def attributes(self) -> NoReturn:
        raise ConcatTypeError(
            format_generic_type_attributes_error(self),
            is_occurs_check_fail=None,
            rigid_variables=None,
        )

    def _free_type_variables(
        self, context: TypeChecker
    ) -> InsertionOrderedSet['Variable']:
        return self._body.free_type_variables(context) - set(
            self._type_parameters
        )


# TODO: Change representation to a tree or a linked list? Flattening code is
# ugly.
class TypeSequence(Type):
    def __init__(self, context: TypeChecker, sequence: Sequence[Type]) -> None:
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
                    t = t.force(context)
                    if isinstance(t, TypeSequence):
                        flattened.extend(t.to_iterator(context))
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

    def force(self, context: TypeChecker) -> None:
        pass

    def force_substitution(
        self, context: TypeChecker, sub: Substitutions
    ) -> 'TypeSequence':
        subbed_types: List[Type] = []
        for type in self.to_iterator(context):
            subbed_type = type.apply_substitution(context, sub)
            if isinstance(subbed_type, TypeSequence):
                subbed_types += [*subbed_type.to_iterator(context)]
            else:
                subbed_types.append(subbed_type)
        return TypeSequence(context, subbed_types)

    @_constrain_on_whnf
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

        if isinstance(supertype, SequenceVariable):
            supertype = TypeSequence(context, [supertype])

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
                    and self._rest
                    not in supertype.free_type_variables(context)
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
                and supertype._rest not in self.free_type_variables(context)
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
                    sub = sub.apply_substitution(
                        context,
                        self.index(context, slice(None, None, -1))
                        .apply_substitution(context, sub)
                        .constrain_and_bind_variables(
                            context,
                            supertype.index(
                                context, slice(None, None, -1)
                            ).apply_substitution(context, sub),
                            rigid_variables,
                            subtyping_assumptions,
                        ),
                    )
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

    def _free_type_variables(
        self, context: TypeChecker
    ) -> InsertionOrderedSet['Variable']:
        ftv: InsertionOrderedSet[Variable] = InsertionOrderedSet([])
        for t in self.to_iterator(context):
            ftv |= t.free_type_variables(context)
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
    def index(self, context: TypeChecker, key: int) -> Type: ...

    @overload
    def index(self, context: TypeChecker, key: slice) -> 'TypeSequence': ...

    def index(self, context: TypeChecker, key: Union[int, slice]) -> Type:
        if isinstance(key, int):
            return self.as_sequence()[key]
        return TypeSequence(context, self.as_sequence()[key])

    def to_user_string(self, context: TypeChecker) -> str:
        return (
            '['
            + ', '.join(
                t.to_user_string(context) for t in self.to_iterator(context)
            )
            + ']'
        )

    def to_string_for_stack_effect(self, context: TypeChecker) -> str:
        return ' '.join(
            t.to_user_string(context) for t in self.to_iterator(context)
        )

    def __repr__(self) -> str:
        return (
            'TypeSequence(['
            + ', '.join(repr(t) for t in self.to_iterator(context))
            + '])'
        )

    def force_repr(self, context: TypeChecker) -> str:
        return (
            'TypeSequence(['
            + ', '.join(
                t.force_repr(context) for t in self.to_iterator(context)
            )
            + '])'
        )

    def to_iterator(self, _context: TypeChecker) -> Iterator[Type]:
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
        input_types: Type,
        output_types: Type,
    ) -> None:
        super().__init__()
        self.input = input_types
        self.output = output_types

    def to_iterator(self, _context: TypeChecker) -> Iterator[Type]:
        return iter((self.input, self.output))

    def generalized_wrt(
        self, context: TypeChecker, gamma: 'Environment'
    ) -> Type:
        parameters = list(
            self.free_type_variables(context)
            - gamma.free_type_variables(context)
        )
        return GenericType(parameters, self)

    @_constrain_on_whnf
    def constrain_and_bind_variables(
        self,
        context: TypeChecker,
        supertype: Type,
        rigid_variables: AbstractSet['Variable'],
        subtyping_assumptions: List[Tuple['Type', 'Type']],
    ) -> 'Substitutions':
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
        sub = sub.apply_substitution(
            context,
            self.output.apply_substitution(
                context, sub
            ).constrain_and_bind_variables(
                context,
                supertype.output.apply_substitution(context, sub),
                rigid_variables,
                subtyping_assumptions,
            ),
        )
        return sub

    def _free_type_variables(
        self, context: TypeChecker
    ) -> InsertionOrderedSet['Variable']:
        return self.input.free_type_variables(
            context
        ) | self.output.free_type_variables(context)

    def __repr__(self) -> str:
        return 'StackEffect({!r}, {!r})'.format(self.input, self.output)

    def force(self, context: TypeChecker) -> None:
        pass

    def force_repr(self, context: TypeChecker) -> str:
        return f'StackEffect({self.input.force_repr(context)}, {self.output.force_repr(context)})'

    def to_user_string(self, context: TypeChecker) -> str:
        in_types = self.input.to_string_for_stack_effect(context)
        out_types = self.output.to_string_for_stack_effect(context)
        return '({} -- {})'.format(in_types, out_types)

    def attributes(self, context: TypeChecker) -> Mapping[str, 'StackEffect']:
        return {'__call__': self}

    def force_substitution(
        self, context: TypeChecker, sub: Substitutions
    ) -> 'StackEffect':
        return StackEffect(
            self.input.apply_substitution(context, sub),
            self.output.apply_substitution(context, sub),
        )

    def bind(self, context: TypeChecker) -> 'StackEffect':
        return StackEffect(
            self.input.index(context, slice(None, None, -1)), self.output
        )


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
            quotation_iterable_type = context.iterable_type.apply(
                context,
                [
                    StackEffect(
                        TypeSequence(context, [in_var]),
                        TypeSequence(context, [out_var]),
                    )
                ],
            )
            return quotation_iterable_type.constrain_and_bind_variables(
                context, supertype, rigid_variables, subtyping_assumptions
            )
        except ConcatTypeError:
            return super().constrain_and_bind_variables(
                context, supertype, rigid_variables, subtyping_assumptions
            )

    @_sub_cache
    def apply_substitution(
        self, context: TypeChecker, sub: Substitutions
    ) -> 'QuotationType':
        return QuotationType(super().apply_substitution(context, sub))

    def __repr__(self) -> str:
        return f'QuotationType({StackEffect(self.input, self.output)!r})'

    def force_repr(self, context: TypeChecker) -> str:
        return f'QuotationType({StackEffect(self.input, self.output).force_repr(context)})'


StackItemType = Union[SequenceVariable, IndividualType]


def free_type_variables_of_mapping(
    context: TypeChecker,
    attributes: Mapping[str, Type],
) -> InsertionOrderedSet[Variable]:
    ftv: InsertionOrderedSet[Variable] = InsertionOrderedSet([])
    for sigma in attributes.values():
        ftv |= sigma.free_type_variables(context)
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

    def to_user_string(self) -> str:
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

    def _free_type_variables(
        self, context: TypeChecker
    ) -> InsertionOrderedSet[Variable]:
        return self._ty.free_type_variables(context)

    def force(self, context: TypeChecker) -> None:
        pass

    def force_substitution(
        self, context: TypeChecker, sub: 'Substitutions'
    ) -> 'NominalType':
        return NominalType(
            self._brand, self._ty.apply_substitution(context, sub)
        )

    def apply(self, _context: TypeChecker, args: TypeArguments) -> Type:
        # Since these types are compared by name, we don't need to perform
        # substitution. Just remember the arguments.
        return TypeApplication(self, args)

    def apply_is_redex(self) -> bool:
        return True

    def force_apply(self, context: TypeChecker, args: TypeArguments) -> Type:
        return NominalType(self._brand, self._ty.apply(context, args))

    def attributes(self, context: TypeChecker) -> Mapping[str, Type]:
        return self._ty.attributes(context)

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
                supertype.force(context),
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

    def brand(self, _context: TypeChecker) -> Brand:
        return self._brand

    def to_user_string(self, _context: TypeChecker) -> str:
        return str(self._brand)

    def __repr__(self) -> str:
        return f'NominalType({self._brand!r}, {self._ty!r})'

    def force_repr(self, context: TypeChecker) -> str:
        return f'NominalType({self._brand!r}, {self._ty.force_repr(context)})'


class ObjectType(IndividualType):
    """Structural record types."""

    def __init__(self, attributes: Mapping[str, Type]) -> None:
        super().__init__()

        self._attributes = attributes

    @property
    def kind(self) -> 'Kind':
        return IndividualKind

    def force(self, context: TypeChecker) -> Type | None:
        for t in self.attributes(context).values():
            if (t.force(context) or t)._type_id == no_return_type._type_id:
                return no_return_type
        return None

    def force_substitution(
        self,
        context: TypeChecker,
        sub: Substitutions,
    ) -> 'ObjectType':
        attributes = cast(
            Dict[str, IndividualType],
            {
                attr: t.apply_substitution(context, sub)
                for attr, t in self._attributes.items()
            },
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
                context,
                '__call__',
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
                    context,
                    '__call__',
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
                supertype.force(context) or supertype,
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
            type = self.get_type_of_attribute(context, name)
            sub = sub.apply_substitution(
                context,
                type.apply_substitution(
                    context, sub
                ).constrain_and_bind_variables(
                    context,
                    supertype.get_type_of_attribute(
                        context, name
                    ).apply_substitution(context, sub),
                    rigid_variables,
                    subtyping_assumptions,
                ),
            )
        sub.add_subtyping_provenance((self, supertype))
        return sub

    def __repr__(self) -> str:
        return f'{type(self).__qualname__}(attributes={self._attributes!r})'

    def force_repr(self, context: TypeChecker) -> str:
        attributes = _mapping_to_str(
            {a: t.force_repr(context) for a, t in self._attributes.items()}
        )
        return f'{type(self).__qualname__}(attributes={attributes})'

    def _free_type_variables(
        self, context: TypeChecker
    ) -> InsertionOrderedSet[Variable]:
        ftv = free_type_variables_of_mapping(context, self.attributes(context))
        # QUESTION: Include supertypes?
        return ftv

    def to_user_string(self, _context: TypeChecker) -> str:
        if self._internal_name is not None:
            return self._internal_name
        return f'ObjectType({_mapping_to_str(self._attributes)})'

    def attributes(self, context: TypeChecker) -> Mapping[str, Type]:
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
            supertype = supertype.force(context) or supertype
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
            sub = sub.apply_substitution(
                context,
                subty.apply_substitution(
                    context, sub
                ).constrain_and_bind_variables(
                    context,
                    superty.apply_substitution(context, sub),
                    rigid_variables,
                    subtyping_assumptions,
                ),
            )
        sub.add_subtyping_provenance((self, supertype))
        return sub

    def _free_type_variables(
        self, context: TypeChecker
    ) -> InsertionOrderedSet[Variable]:
        return functools.reduce(
            operator.or_,
            (t.free_type_variables(context) for t in self._types),
            InsertionOrderedSet([]),
        )

    def force(self, context: TypeChecker) -> None:
        pass

    def force_substitution(self, context: TypeChecker, sub) -> TypeTuple:
        return TypeTuple(
            [t.apply_substitution(context, sub) for t in self._types]
        )

    @property
    def attributes(self) -> NoReturn:
        raise TypeError(format_cannot_have_attributes_error(self))

    @property
    def kind(self) -> TupleKind:
        return TupleKind([t.kind for t in self._types])

    def project(self, _context: TypeChecker, n: int) -> Type:
        assert n < len(
            self._types
        ), format_type_tuple_index_out_of_range_error(self, n)
        return self._types[n]

    def __repr__(self) -> str:
        return f'TypeTuple({self._types!r})'

    def force_repr(self, context: TypeChecker) -> str:
        return f'TypeTuple({
            _iterable_to_str(t.force_repr(context) for t in self._types)
        })'

    def to_user_string(self, context: TypeChecker) -> str:
        return f'({','.join(str(t) for t in self._types)})'


class DelayedSubstitution(Type):
    def __init__(
        self, context: TypeChecker, sub: Substitutions, ty: Type
    ) -> None:
        super().__init__()
        self._sub: Substitutions
        self._ty: Type
        if isinstance(ty, DelayedSubstitution):
            sub = ty._sub.apply_substitution(context, sub)
            ty = ty._ty
        self._sub = Substitutions(
            {
                v: t
                for v, t in sub.items()
                if v in ty.free_type_variables(context)
            }
        )
        self._ty = ty
        self._forced: Type | None = None

    def project(self, context: TypeChecker, n: int) -> DelayedSubstitution:
        return DelayedSubstitution(
            context, self._sub, self._ty.project(context, n)
        )

    def apply(self, context: TypeChecker, x: Any) -> Type:
        if self.kind <= SequenceKind:
            return self.force(context).index(context, x)
        return DelayedSubstitution(
            context, self._sub, self._ty.apply(context, x)
        )

    def apply_is_redex(self) -> bool:
        return True

    def length(self, context: TypeChecker) -> int:
        return self.force(context).length(context)

    def __bool__(self) -> bool:
        return True

    def instantiate(self, context: TypeChecker) -> DelayedSubstitution:
        return DelayedSubstitution(
            context, self._sub, self._ty.instantiate(context)
        )

    def __repr__(self) -> str:
        return f'DelayedSubstitution({self._sub!r}, {self._ty!r})'

    def force_repr(self, context: TypeChecker) -> str:
        return self.force(context).force_repr(context)

    def to_user_string(self, context: TypeChecker) -> str:
        return str(self.force(context))

    def _free_type_variables(
        self, context: TypeChecker
    ) -> InsertionOrderedSet[Variable]:
        return functools.reduce(
            operator.or_,
            (
                v.apply_substitution(context, self._sub).free_type_variables(
                    context
                )
                for v in self._ty.free_type_variables(context)
            ),
            InsertionOrderedSet([]),
        )

    @_sub_cache
    def apply_substitution(
        self, context: TypeChecker, sub: Substitutions
    ) -> Type:
        return DelayedSubstitution(
            context, self._sub.apply_substitution(context, sub), self._ty
        )

    def force_substitution(
        self, context: TypeChecker, sub: Substitutions
    ) -> Type:
        return self.apply_substitution(context, sub)

    def attributes(self, context: TypeChecker) -> Mapping[str, Type]:
        return self.force(context).attributes(context)

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
        return self.force(context).constrain_and_bind_variables(
            context, supertype, rigid_variables, subtyping_assumptions
        )

    @property
    def kind(self) -> Kind:
        return self._ty.kind

    def force(self, context: TypeChecker) -> Type:
        if not self._forced:
            self._forced = self._ty.force_substitution(context, self._sub)
            self._forced._type_id = self._type_id
            assert not isinstance(
                self._forced, DelayedSubstitution
            ), f'{self._ty!r}'
        return self._forced.force(context) or self._forced

    def to_iterator(
        self, context: TypeChecker
    ) -> Iterator[DelayedSubstitution]:
        assert isinstance(self._ty, (StackEffect, TypeSequence))
        for component in self._ty.to_iterator(context):
            yield DelayedSubstitution(context, self._sub, component)

    def input(self, context: TypeChecker) -> DelayedSubstitution:
        assert isinstance(self._ty, (StackEffect, PythonFunctionType))
        return DelayedSubstitution(context, self._sub, self._ty.input)

    def output(self, context: TypeChecker) -> DelayedSubstitution:
        assert isinstance(self._ty, (StackEffect, PythonFunctionType))
        return DelayedSubstitution(context, self._sub, self._ty.output)

    def arguments(self, context: TypeChecker) -> Sequence[Type]:
        ty = self.force(context)
        assert isinstance(ty, VariableArgumentPack)
        return ty.arguments


class VariableArgumentPack(Type):
    """List of types passed as an argument in a variable-length argument \
    position."""

    def __init__(self, types: Sequence[Type]) -> None:
        super().__init__()
        self._types = types

    def to_user_string(self, _context: TypeChecker) -> str:
        return f'variable-length arguments {', '.join(str(t) for t in self._types)}'

    def __repr__(self) -> str:
        return f'VariableArgumentPack({self._types!r})'

    def force(self, context: TypeChecker) -> None:
        pass

    def force_repr(self, context: TypeChecker) -> str:
        return f'VariableArgumentPack({_iterable_to_str(t.force_repr(context) for t in self._types)})'

    @property
    def arguments(self) -> Sequence[Type]:
        return self._types

    @classmethod
    def collect_arguments(
        cls, context: TypeChecker, args: Iterable[Type]
    ) -> VariableArgumentPack:
        flattened_args: list[Type] = []
        for arg in args:
            if isinstance(arg, DelayedSubstitution):
                arg = arg.force(context)
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
            and supertype not in self.free_type_variables(context)
        ):
            return Substitutions([(supertype, self)])
        if not isinstance(supertype, VariableArgumentPack):
            raise NotImplementedError
        sub = Substitutions()
        for subty, superty in zip(self._types, supertype._types):
            sub = sub.apply_substitution(
                context,
                subty.apply_substitution(
                    context, sub
                ).constrain_and_bind_variables(
                    context,
                    superty.apply_substitution(context, sub),
                    rigid_variables,
                    subtyping_assumptions,
                ),
            )
        sub.add_subtyping_provenance((self, supertype))
        return sub

    def _free_type_variables(
        self, context: TypeChecker
    ) -> InsertionOrderedSet[Variable]:
        return functools.reduce(
            operator.or_,
            (t.free_type_variables(context) for t in self._types),
            InsertionOrderedSet([]),
        )

    def force_substitution(
        self, context: TypeChecker, sub
    ) -> VariableArgumentPack:
        return VariableArgumentPack.collect_arguments(
            context, [t.apply_substitution(context, sub) for t in self._types]
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
            supertype = supertype.force(context)
        if (
            not supertype.has_attribute('__call__')
            or '__init__' not in self._attributes
        ):
            sub = super().constrain_and_bind_variables(
                context, supertype, rigid_variables, subtyping_assumptions
            )
            sub.add_subtyping_provenance((self, supertype))
            return sub
        init = self.get_type_of_attribute(context, '__init__')
        # FIXME: Use constraint to allow more kinds of type rep
        while not isinstance(init, (StackEffect, PythonFunctionType)):
            init = init.get_type_of_attribute(context, '__call__')
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
        context: TypeChecker,
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
        if (
            isinstance(i, TypeSequence)
            and i
            and i.as_sequence()[0].kind == SequenceKind
        ):
            i = TypeSequence(context, i.as_sequence()[1:])
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

    def force(self, context: TypeChecker) -> None:
        pass

    def force_repr(self) -> str:
        return (
            f'PythonFunctionType(inputs={self.input.force_repr()}, '
            f'output={self.output.force_repr()})'
        )

    def to_user_string(self) -> str:
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

    def apply(self, args: Sequence[Type]) -> NoReturn:
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

    def force(self, context: TypeChecker) -> Type | None:
        overloads = self._overloads.arguments
        if not overloads:
            return context.object_type
        # for i, t in enumerate(self._overloads.arguments):
        #     try:
        #         sub = t.constrain_and_bind_variables(context, no_return_type, set(), [])
        #     except ConcatTypeError:
        #         pass
        #     if set(sub) & t.free_type_variables():
        #         return no_return_type
        #     # FIXME: Should look backwards, but not remove both of pairs of
        #     # isomorphic types.
        #     for s in self._overloads.arguments[i + 1:]:
        #         try:
        #             sub = t.constrain_and_bind_variables(context, s, set(), [])
        #         except ConcatTypeError:
        #             overloads.append(t)
        #             continue
        #         if set(sub) & (t.free_type_variables() | s.free_type_variables()):
        #             overloads.append(t)
        if len(overloads) == 1:
            return overloads[0]
        if any(t._type_id == no_return_type._type_id for t in overloads):
            return no_return_type
        return None

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
            supertype = supertype.force(context)
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
            for attr in supertype.attributes(context):
                self_attr_type = self.get_type_of_attribute(
                    context, attr
                ).apply_substitution(context, sub)
                supertype_attr_type = supertype.get_type_of_attribute(
                    context, attr
                ).apply_substitution(context, sub)
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
                    [
                        (
                            self._overloads.arguments[0],
                            TypeSequence(context, [supertype]),
                        )
                    ]
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

    def to_user_string(self, context: TypeChecker) -> str:
        return f'py_overloaded[{', '.join(str(t) for t in self._overloads.arguments)}]'

    def __repr__(self) -> str:
        return f'_PythonOverloadedType({self._overloads!r})'

    def force_repr(self, context: TypeChecker) -> str:
        return f'_PythonOverloadedType({self._overloads.force_repr(context)})'

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
    def apply_substitution(
        self, context: TypeChecker, sub: Substitutions
    ) -> '_NoReturnType':
        return self

    def force(self, context: TypeChecker) -> None:
        pass

    def force_substitution(
        self, context: TypeChecker, sub: Substitutions
    ) -> _NoReturnType:
        return self.apply_substitution(context, sub)

    def __repr__(self) -> str:
        return '_NoReturnType()'

    def force_repr(self, _context: TypeChecker) -> str:
        return repr(self)

    def _free_type_variables(
        self, _context: TypeChecker
    ) -> InsertionOrderedSet['Variable']:
        return InsertionOrderedSet([])

    def attributes(self, context: TypeChecker) -> Mapping[str, Type]:
        return defaultdict(lambda: self)


class _OptionalType(IndividualType):
    def __init__(self, type_argument: Type) -> None:
        super().__init__()
        if not (type_argument.kind <= ItemKind):
            raise ConcatTypeError(
                format_must_be_item_type_error(type_argument),
                is_occurs_check_fail=None,
                rigid_variables=None,
            )
        self._type_argument: Type = type_argument

    def attributes(self, context: TypeChecker) -> Mapping[str, Type]:
        # NOTE: this might not be complete as it should be
        raise ConcatTypeError(
            format_attributes_unknown_error(self),
            is_occurs_check_fail=False,
            rigid_variables=None,
        )

    def __repr__(self) -> str:
        return f'_OptionalType({self._type_argument!r})'

    def force(self, context: TypeChecker) -> Type | None:
        type_argument = self._type_argument
        while isinstance(type_argument, _OptionalType):
            type_argument = type_argument._type_argument
        if (
            type_argument.force(context) or type_argument
        )._type_id == context.none_type._type_id:
            return context.none_type
        if type_argument._type_id == self._type_argument._type_id:
            return None
        return _OptionalType(type_argument)

    def force_repr(self, context: TypeChecker) -> str:
        return f'_OptionalType({self._type_argument.force_repr(context)})'

    def to_user_string(self, _context: TypeChecker) -> str:
        return f'optional_type[{self._type_argument}]'

    def _free_type_variables(
        self, context: TypeChecker
    ) -> InsertionOrderedSet[Variable]:
        return self._type_argument.free_type_variables(context)

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
        sub = self._type_argument.apply_substitution(
            context, sub
        ).constrain_and_bind_variables(
            context,
            supertype.apply_substitution(context, sub),
            rigid_variables,
            subtyping_assumptions,
        )
        return sub

    def force_substitution(
        self, context: TypeChecker, sub: Substitutions
    ) -> '_OptionalType':
        return _OptionalType(
            self._type_argument.apply_substitution(context, sub)
        )

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

    def force(self, context: TypeChecker) -> Type | None:
        if self._var in self._body.free_type_variables(context):
            return None
        return self._body.force(context) or self._body

    def force_repr(self, context: TypeChecker) -> str:
        return f'Fix({self._var!r}, {self._body.force_repr(context)})'

    def to_user_string(self, _context: TypeChecker) -> str:
        if self._internal_name is not None:
            return self._internal_name
        return f'Fix({self._var}, {self._body})'

    def _apply(self, context: TypeChecker, t: Type) -> Type:
        if t._type_id not in self._cache:
            sub = Substitutions([(self._var, t)])
            self._cache[t._type_id] = self._body.apply_substitution(
                context, sub
            )
            assert self._var not in self._cache[
                t._type_id
            ].free_type_variables(context)
        return self._cache[t._type_id]

    def unroll(self, context: TypeChecker) -> Type:
        if self._unrolled_ty is None:
            self._unrolled_ty = self._apply(context, self)
            if self._internal_name is not None:
                self._unrolled_ty.set_internal_name(self._internal_name)
            # Do not make the type ids equal so that subtyping assumptions are
            # useful
        return self._unrolled_ty

    def _free_type_variables(
        self, context: TypeChecker
    ) -> InsertionOrderedSet[Variable]:
        return self._body.free_type_variables(context) - {self._var}

    def force_substitution(
        self, context: TypeChecker, sub: 'Substitutions'
    ) -> Type:
        sub = Substitutions(
            {v: t for v, t in sub.items() if v is not self._var}
        )

        return Fix(self._var, self._body.apply_substitution(context, sub))

    def attributes(self, context: TypeChecker) -> Mapping[str, Type]:
        return self.unroll(context).attributes(context)

    def constrain_and_bind_variables(
        self,
        context: TypeChecker,
        supertype,
        rigid_variables,
        subtyping_assumptions,
    ) -> 'Substitutions':
        _logger.debug('{} <:? {}', self, supertype)
        if isinstance(supertype, DelayedSubstitution):
            supertype = supertype.force(context)
        if (
            supertype._type_id == context.object_type._type_id
            or _contains_assumption(subtyping_assumptions, self, supertype)
        ):
            sub = Substitutions()
            sub.add_subtyping_provenance((self, supertype))
            return sub

        if isinstance(supertype, Fix):
            unrolled = supertype.unroll(context)
            sub = self.unroll(context).constrain_and_bind_variables(
                context,
                unrolled,
                rigid_variables,
                subtyping_assumptions + [(self, supertype)],
            )
            sub.add_subtyping_provenance((self, supertype))
            return sub

        sub = self.unroll(context).constrain_and_bind_variables(
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

    def apply(self, context: TypeChecker, args: Any) -> Any:
        if isinstance(self._body, NominalType):
            return TypeApplication(self, args)
        return self.unroll(context).apply(context, args)

    def apply_is_redex(self) -> bool:
        return isinstance(self._body, NominalType)

    def force_apply(self, context: TypeChecker, args: Any) -> Any:
        return self.unroll(context).apply(context, args)

    def project_is_redex(self) -> bool:
        return True

    def force_project(self, context: TypeChecker, i: int) -> Type:
        return self.unroll(context).project(context, i)

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
