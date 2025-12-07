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
from concat.typecheck.context import current_context
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
    format_not_a_list_of_type_arguments_error,
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

    @functools.wraps(f)
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
    [T, TypeChecker, Type, AbstractSet[Variable], Sequence[tuple[Type, Type]]],
    None,
]


def _constrain_on_whnf[T: Type](f: _ConstrainFn[T]) -> _ConstrainFn[T]:
    @functools.wraps(f)
    def constrain_and_bind_variables(
        self,
        context: TypeChecker,
        supertype: Type,
        rigid_variables: AbstractSet['Variable'],
        subtyping_assumptions: Sequence[tuple[Type, Type]],
    ) -> None:
        forced = self.force(context)
        supertype = supertype.force_if_possible(context)
        if forced is not None:
            return forced.constrain_and_bind_variables(
                context,
                supertype,
                rigid_variables,
                subtyping_assumptions,
            )
        return f(
            self,
            context,
            supertype,
            rigid_variables,
            subtyping_assumptions,
        )

    return constrain_and_bind_variables


def _whnf_self[T: Type, **K, R](
    f: Callable[Concatenate[T, TypeChecker, K], R],
) -> Callable[Concatenate[T, TypeChecker, K], R]:
    @functools.wraps(f)
    def g(
        self: T, context: TypeChecker, *args: K.args, **kwargs: K.kwargs
    ) -> R:
        forced = self.force(context)
        if forced is not None:
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

    def is_object_type(self, context: TypeChecker) -> bool:
        ty = self.force_if_possible(context)
        try:
            brand = ty.brand(context)
        except ConcatTypeError:
            return False
        return brand is context.object_type.brand(context)

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
        self = self.force_if_possible(context)
        other = other.force_if_possible(context)
        # QUESTION: Define == separately from subtyping code?
        ftv = self.free_type_variables(context) | other.free_type_variables(
            context
        )
        with context.substitutions.push() as new_subs:
            try:
                self.constrain_and_bind_variables(context, other, set(), [])
                other.constrain_and_bind_variables(context, self, set(), [])
            except StaticAnalysisError:
                return False
        new_subs = Substitutions(
            {v: t for v, t in new_subs.items() if v in ftv}
        )
        return not new_subs

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
            # In the case of self-recursion, there will be no new FTVs, so we
            # can pretend there are none until we finish finding the others.
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
        supertype: Type,
        rigid_variables: AbstractSet[Variable],
        subtyping_assumptions: Sequence[tuple[Type, Type]],
    ) -> None:
        raise NotImplementedError

    # I don't use functools.singledispatch because of static typing issues. For
    # example, see https://github.com/microsoft/pylance-release/issues/4277.

    def _constrain_as_supertype_of_item_variable(
        self,
        context: TypeChecker,
        subtype: ItemVariable,
        rigid_variables: AbstractSet[Variable],
        subtyping_assumptions: Sequence[tuple[Type, Type]],
    ) -> None:
        if subtype in rigid_variables:
            raise ConcatTypeError(
                format_rigid_variable_error(subtype, self),
                is_occurs_check_fail=False,
                rigid_variables=rigid_variables,
            )
        if subtype.kind >= self.kind:
            # FIXME: occurs check!
            context.substitutions[subtype] = self
            return
        raise ConcatTypeError(
            format_subkinding_error(self, subtype),
            is_occurs_check_fail=False,
            rigid_variables=rigid_variables,
        )

    def _constrain_as_supertype_of_sequence_variable(
        self,
        context: TypeChecker,
        subtype: SequenceVariable,
        rigid_variables: AbstractSet[Variable],
        subtyping_assumptions: Sequence[tuple[Type, Type]],
    ) -> None:
        if subtype in rigid_variables:
            raise ConcatTypeError(
                format_rigid_variable_error(subtype, self),
                is_occurs_check_fail=False,
                rigid_variables=rigid_variables,
            )
        # occurs check
        if subtype in self.free_type_variables(context):
            raise ConcatTypeError(
                format_occurs_error(subtype, self),
                is_occurs_check_fail=True,
                rigid_variables=rigid_variables,
            )
        context.substitutions[subtype] = self

    def _constrain_as_supertype_of_generic(
        self,
        context: TypeChecker,
        subtype: GenericType,
        rigid_variables: AbstractSet[Variable],
        subtyping_assumptions: Sequence[tuple[Type, Type]],
    ) -> None:
        supertype_parameter_kinds: list[Kind]
        if isinstance(self.kind, GenericTypeKind):
            supertype_parameter_kinds = [*self.kind.parameter_kinds]
        elif subtype.kind.result_kind <= self.kind:
            supertype_parameter_kinds = []
        else:
            raise ConcatTypeError(
                format_subkinding_error(subtype, self),
                is_occurs_check_fail=None,
                rigid_variables=rigid_variables,
            )
        params_to_inst = len(subtype.kind.parameter_kinds) - len(
            supertype_parameter_kinds
        )
        if params_to_inst == 0:
            fresh_args = [t.freshen() for t in subtype._type_parameters]
            return self.apply(
                context, fresh_args
            ).constrain_and_bind_variables(
                context,
                self.apply(context, fresh_args),
                rigid_variables,
                subtyping_assumptions,
            )

        param_kinds_left = [
            *subtype.kind.parameter_kinds[-len(supertype_parameter_kinds) :]
        ]
        if params_to_inst < 0 or not (
            param_kinds_left >= supertype_parameter_kinds
        ):
            raise ConcatTypeError(
                format_subkinding_error(subtype, self),
                is_occurs_check_fail=None,
                rigid_variables=rigid_variables,
            )
        sub = Substitutions(
            [
                (t, t.freshen())
                for t in subtype._type_parameters[:params_to_inst]
            ]
        )
        parameters_left = subtype._type_parameters[params_to_inst:]
        inst: Type
        if parameters_left:
            inst = GenericType(
                parameters_left,
                subtype._body.apply_substitution(context, sub),
            )
        else:
            inst = subtype._body.apply_substitution(context, sub)
        return inst.constrain_and_bind_variables(
            context, self, rigid_variables, subtyping_assumptions
        )

    def _constrain_as_supertype_of_variable_argument_pack(
        self,
        context: TypeChecker,
        subtype: VariableArgumentPack,
        rigid_variables: AbstractSet[Variable],
        subtyping_assumptions: Sequence[tuple[Type, Type]],
    ) -> None:
        raise NotImplementedError

    def _constrain_as_supertype_of_fixpoint(
        self,
        context: TypeChecker,
        subtype: Fix,
        rigid_variables: AbstractSet[Variable],
        subtyping_assumptions: Sequence[tuple[Type, Type]],
    ) -> None:
        subtype.unroll(context).constrain_and_bind_variables(
            context,
            self,
            rigid_variables,
            [*subtyping_assumptions, (subtype, self)],
        )

    def _constrain_as_supertype_of_stack_effect(
        self,
        context: TypeChecker,
        subtype: StackEffect,
        rigid_variables: AbstractSet[Variable],
        subtyping_assumptions: Sequence[tuple[Type, Type]],
    ) -> None:
        raise ConcatTypeError(
            format_subtyping_error(context, subtype, self),
            is_occurs_check_fail=None,
            rigid_variables=rigid_variables,
        )

    def _constrain_as_supertype_of_py_function_type(
        self,
        context: TypeChecker,
        subtype: PythonFunctionType,
        rigid_variables: AbstractSet[Variable],
        subtyping_assumptions: Sequence[tuple[Type, Type]],
    ) -> None:
        if not (subtype.kind <= self.kind):
            raise ConcatTypeError(
                format_subkinding_error(subtype, self),
                is_occurs_check_fail=False,
                rigid_variables=rigid_variables,
            )
        raise NotImplementedError

    def _constrain_as_supertype_of_object_type(
        self,
        context: TypeChecker,
        subtype: ObjectType,
        rigid_variables: AbstractSet[Variable],
        subtyping_assumptions: Sequence[tuple[Type, Type]],
    ) -> None:
        if not (subtype.kind <= self.kind):
            raise ConcatTypeError(
                format_subkinding_error(subtype, self),
                is_occurs_check_fail=False,
                rigid_variables=rigid_variables,
            )
        raise NotImplementedError

    def _constrain_as_supertype_of_type_sequence(
        self,
        context: TypeChecker,
        subtype: TypeSequence,
        rigid_variables: AbstractSet[Variable],
        subtyping_assumptions: Sequence[tuple[Type, Type]],
    ) -> None:
        if self.kind >= subtype.kind:
            raise NotImplementedError
        raise ConcatTypeError(
            format_subkinding_error(subtype, self),
            is_occurs_check_fail=False,
            rigid_variables=rigid_variables,
        )

    def _constrain_as_supertype_of_py_overloaded_type(
        self,
        context: TypeChecker,
        subtype: PythonOverloadedType,
        rigid_variables: AbstractSet[Variable],
        subtyping_assumptions: Sequence[tuple[Type, Type]],
    ) -> None:
        if self.kind >= subtype.kind:
            raise NotImplementedError
        raise ConcatTypeError(
            format_subkinding_error(subtype, self),
            is_occurs_check_fail=False,
            rigid_variables=rigid_variables,
        )

    def _constrain_as_supertype_of_optional_type(
        self,
        context: TypeChecker,
        subtype: OptionalType,
        rigid_variables: AbstractSet[Variable],
        subtyping_assumptions: Sequence[tuple[Type, Type]],
    ) -> None:
        context.none_type.constrain_and_bind_variables(
            context, self, rigid_variables, subtyping_assumptions
        )
        subtype._type_argument.constrain_and_bind_variables(
            context,
            self,
            rigid_variables,
            subtyping_assumptions,
        )

    def _constrain_as_supertype_of_projection(
        self,
        context: TypeChecker,
        subtype: Projection,
        rigid_variables: AbstractSet[Variable],
        subtyping_assumptions: Sequence[tuple[Type, Type]],
    ) -> None:
        if self.kind >= subtype.kind:
            raise NotImplementedError
        raise ConcatTypeError(
            format_subtyping_error(context, subtype, self),
            is_occurs_check_fail=None,
            rigid_variables=rigid_variables,
        )

    def _constrain_as_supertype_of_nominal_type(
        self,
        context: TypeChecker,
        subtype: NominalType,
        rigid_variables: AbstractSet[Variable],
        subtyping_assumptions: Sequence[tuple[Type, Type]],
    ) -> None:
        return subtype._ty.constrain_and_bind_variables(
            context, self, rigid_variables, subtyping_assumptions
        )

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

    def force_if_possible(self, context: TypeChecker) -> Type:
        forced = self.force(context)
        if forced is None:
            return self
        return forced

    @abc.abstractmethod
    def force_repr(self, context: TypeChecker) -> str:
        pass

    def __getitem__(self, args: TypeArguments) -> Type:
        context = current_context.get()
        return self.apply(context, args)

    def apply(self, context: TypeChecker, _: TypeArguments) -> Type:
        _logger.debug('tried to treat {} as generic', self)
        raise ConcatTypeError(
            format_not_generic_type_error(self),
            is_occurs_check_fail=None,
            rigid_variables=None,
        )

    @overload
    def index(self, context: TypeChecker, i: int) -> Type: ...

    @overload
    def index(self, context: TypeChecker, i: slice) -> TypeSequence: ...

    def index(self, context: TypeChecker, i: int | slice) -> Type:
        forced = self.force(context)
        if forced is not None:
            return forced.index(context, i)
        raise ConcatTypeError(
            format_not_a_sequence_type_error(context, self),
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

    @_whnf_self
    def brand(self, _context: TypeChecker) -> Brand:
        raise ConcatTypeError(
            format_not_a_nominal_type_error(self),
            is_occurs_check_fail=None,
            rigid_variables=None,
        )

    def as_sequence(self) -> Sequence[Type]:
        context = current_context.get()
        forced = self.force(context)
        if forced is not None:
            return forced.as_sequence()
        raise ConcatTypeError(
            format_not_a_sequence_type_error(context, self),
            is_occurs_check_fail=False,
            rigid_variables=None,
        )

    @property
    def arguments(self) -> Sequence[Type]:
        context = current_context.get()
        forced = self.force(context)
        if forced is not None:
            return forced.arguments
        if self.kind <= VariableArgumentKind(TopKind):
            return [self]
        raise ConcatTypeError(
            format_not_a_list_of_type_arguments_error(context, self),
            is_occurs_check_fail=False,
            rigid_variables=None,
        )


class IndividualType(Type):
    @property
    def kind(self) -> 'Kind':
        return IndividualKind


class TypeApplication(Type):
    def __init__(self, head: Type, args: 'TypeArguments') -> None:
        context = current_context.get()
        super().__init__()
        if not isinstance(head.kind, GenericTypeKind):
            raise ConcatTypeError(
                format_not_generic_type_error(head),
                is_occurs_check_fail=None,
                rigid_variables=None,
            )
        if len(head.kind.parameter_kinds) == 1 and (
            head.kind.parameter_kinds[0] <= VariableArgumentKind(TopKind)
        ):
            args = [VariableArgumentPack.collect_arguments(context, args)]
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
        return forced.force_if_possible(context)

    @_constrain_on_whnf
    def constrain_and_bind_variables(
        self,
        context: TypeChecker,
        supertype,
        rigid_variables,
        subtyping_assumptions,
    ) -> None:
        if (
            self._type_id == supertype._type_id
            or (
                self._result_kind <= IndividualKind
                and supertype.is_object_type(context)
            )
            or _contains_assumption(subtyping_assumptions, self, supertype)
        ):
            return
        return supertype._constrain_as_supertype_of_type_application(
            context,
            self,
            rigid_variables,
            subtyping_assumptions,
        )

    def _constrain_as_supertype_of_type_sequence(
        self,
        context: TypeChecker,
        subtype: TypeSequence,
        rigid_variables: AbstractSet[Variable],
        subtyping_assumptions: Sequence[tuple[Type, Type]],
    ) -> None:
        raise ConcatTypeError(
            format_subtyping_error(context, subtype, self),
            is_occurs_check_fail=False,
            rigid_variables=rigid_variables,
        )

    def _constrain_as_supertype_of_type_application(
        self,
        context: TypeChecker,
        subtype: TypeApplication,
        rigid_variables: AbstractSet[Variable],
        subtyping_assumptions: Sequence[tuple[Type, Type]],
    ) -> None:
        # TODO: Variance
        return subtype._head.constrain_and_bind_variables(
            context,
            self._head,
            rigid_variables,
            subtyping_assumptions,
        )

    def is_redex(self) -> bool:
        return self._head.apply_is_redex()

    def force(self, context: TypeChecker) -> Type | None:
        if self.is_redex():
            if not self._forced:
                self._forced = self._head.force_apply(context, self._args)
            return self._forced.force_if_possible(context)
        return None

    def __str__(self) -> str:
        if self._internal_name is not None:
            return self._internal_name
        return f'{self._head}{_iterable_to_str(self._args)}'

    def __repr__(self) -> str:
        return f'TypeApplication({self._head!r}, {self._args!r})'

    @_whnf_self
    def force_repr(self, context: TypeChecker) -> str:
        return (
            f'TypeApplication({self._head.force_repr(context)}, '
            f'{[a.force_repr(context) for a in self._args]})'
        )

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

    @_whnf_self
    def _free_type_variables(
        self, context: TypeChecker
    ) -> InsertionOrderedSet[Variable]:
        return self._head.free_type_variables(context)

    def force_substitution(
        self, context: TypeChecker, sub: Substitutions
    ) -> Type:
        return self._head.force_substitution(context, sub).project(
            context, self._index
        )

    @_whnf_self
    def attributes(self, context: TypeChecker) -> Mapping[str, Type]:
        raise ConcatTypeError(
            format_attributes_unknown_error(self),
            is_occurs_check_fail=None,
            rigid_variables=None,
        )

    @_constrain_on_whnf
    def constrain_and_bind_variables(
        self, context, supertype, rigid_variables, subtyping_assumptions
    ) -> None:
        if (
            self._type_id == supertype._type_id
            or _contains_assumption(subtyping_assumptions, self, supertype)
            or self.kind <= IndividualKind
            and supertype.is_object_type(context)
        ):
            return
        return supertype._constrain_as_supertype_of_projection(
            context,
            self,
            rigid_variables,
            subtyping_assumptions,
        )

    def _constrain_as_supertype_of_projection(
        self,
        context: TypeChecker,
        subtype: Projection,
        rigid_variables: AbstractSet[Variable],
        subtyping_assumptions: Sequence[tuple[Type, Type]],
    ) -> None:
        subtype._head.constrain_and_bind_variables(
            context,
            self._head,
            rigid_variables,
            subtyping_assumptions,
        )
        assert subtype._index == self._index, format_subtyping_error(
            context,
            subtype,
            self,
        )

    def _constrain_as_supertype_of_type_sequence(
        self,
        context: TypeChecker,
        subtype: TypeSequence,
        rigid_variables: AbstractSet[Variable],
        subtyping_assumptions: Sequence[tuple[Type, Type]],
    ) -> None:
        raise ConcatTypeError(
            format_subtyping_error(context, subtype, self),
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
                self._forced = self._forced.force_if_possible(context)
            return self._forced
        return None

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

    def force(self, context: TypeChecker) -> Type | None:
        if self in context.substitutions:
            return context.substitutions[self].force_if_possible(context)
        return None

    def as_sequence(self) -> Sequence[Type]:
        context = current_context.get()
        forced = self.force(context)
        if forced is not None:
            return forced.as_sequence()
        if not (self.kind <= SequenceKind):
            raise ConcatTypeError(
                format_not_a_sequence_type_error(context, self),
                is_occurs_check_fail=False,
                rigid_variables=None,
            )
        return [self]

    def force_substitution(
        self, context: TypeChecker, sub: Substitutions
    ) -> Type:
        result = self.apply_substitution(context, sub)
        return result.force_if_possible(context)

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

    def _constrain_as_supertype_of_item_variable(
        self,
        context: TypeChecker,
        subtype: ItemVariable,
        rigid_variables: AbstractSet[Variable],
        subtyping_assumptions: Sequence[tuple[Type, Type]],
    ) -> None:
        if subtype.kind <= self.kind and self not in rigid_variables:
            context.substitutions[self] = subtype
            return
        super()._constrain_as_supertype_of_item_variable(
            context,
            subtype,
            rigid_variables,
            subtyping_assumptions,
        )

    def _constrain_as_supertype_of_generic(
        self,
        context: TypeChecker,
        subtype: GenericType,
        rigid_variables: AbstractSet[Variable],
        subtyping_assumptions: Sequence[tuple[Type, Type]],
    ) -> None:
        if self in rigid_variables:
            raise ConcatTypeError(
                format_rigid_variable_error(self, subtype),
                is_occurs_check_fail=False,
                rigid_variables=rigid_variables,
            )
        if self in subtype.free_type_variables(context):
            raise ConcatTypeError(
                format_occurs_error(self, subtype),
                is_occurs_check_fail=True,
                rigid_variables=rigid_variables,
            )
        if subtype.kind <= self.kind:
            context.substitutions[self] = subtype
            return
        super()._constrain_as_supertype_of_generic(
            context,
            subtype,
            rigid_variables,
            subtyping_assumptions,
        )

    def _constrain_as_supertype_of_py_function_type(
        self,
        context: TypeChecker,
        subtype: PythonFunctionType,
        rigid_variables: AbstractSet[Variable],
        subtyping_assumptions: Sequence[tuple[Type, Type]],
    ) -> None:
        if self.kind <= ItemKind and self not in rigid_variables:
            if self in subtype.free_type_variables(context):
                raise ConcatTypeError(
                    format_occurs_error(self, subtype),
                    is_occurs_check_fail=True,
                    rigid_variables=rigid_variables,
                )
            context.substitutions[self] = subtype
            return
        raise ConcatTypeError(
            format_subtyping_error(context, subtype, self),
            is_occurs_check_fail=False,
            rigid_variables=rigid_variables,
        )

    def _constrain_as_supertype_of_variable_argument_pack(
        self,
        context: TypeChecker,
        subtype: VariableArgumentPack,
        rigid_variables: AbstractSet[Variable],
        subtyping_assumptions: Sequence[tuple[Type, Type]],
    ) -> None:
        if (
            self not in rigid_variables
            # occurs check!
            and self not in subtype.free_type_variables(context)
        ):
            context.substitutions[self] = subtype
            return
        raise ConcatTypeError(
            format_subtyping_error(context, subtype, self),
            is_occurs_check_fail=None,
            rigid_variables=rigid_variables,
        )

    def _constrain_as_supertype_of_object_type(
        self,
        context: TypeChecker,
        subtype: ObjectType,
        rigid_variables: AbstractSet[Variable],
        subtyping_assumptions: Sequence[tuple[Type, Type]],
    ) -> None:
        # obj <: `t, `t is not rigid
        # --> `t = obj
        if self.kind >= IndividualKind and self not in rigid_variables:
            if self in subtype.free_type_variables(context):
                raise ConcatTypeError(
                    format_occurs_error(self, subtype),
                    is_occurs_check_fail=True,
                    rigid_variables=rigid_variables,
                )
            context.substitutions[self] = subtype
            return
        raise ConcatTypeError(
            format_subtyping_error(context, subtype, self),
            is_occurs_check_fail=False,
            rigid_variables=rigid_variables,
        )

    def _constrain_as_supertype_of_nominal_type(
        self,
        context: TypeChecker,
        subtype: NominalType,
        rigid_variables: AbstractSet[Variable],
        subtyping_assumptions: Sequence[tuple[Type, Type]],
    ) -> None:
        if self in rigid_variables:
            raise ConcatTypeError(
                format_rigid_variable_error(self, subtype),
                is_occurs_check_fail=False,
                rigid_variables=rigid_variables,
            )
        if not (subtype.kind <= self.kind):
            raise ConcatTypeError(
                format_subkinding_error(subtype, self),
                is_occurs_check_fail=False,
                rigid_variables=rigid_variables,
            )
        # FIXME
        # if self in subtype.free_type_variables(context):
        #     raise ConcatTypeError(
        #         format_occurs_error(self, subtype),
        #         is_occurs_check_fail=True,
        #         rigid_variables=rigid_variables,
        #     )
        context.substitutions[self] = subtype

    def _constrain_as_supertype_of_type_application(
        self,
        context: TypeChecker,
        subtype: TypeApplication,
        rigid_variables: AbstractSet[Variable],
        subtyping_assumptions: Sequence[tuple[Type, Type]],
    ) -> Substitutions:
        # occurs check!
        if self.kind >= subtype.kind and self not in rigid_variables:
            if self in subtype.free_type_variables(context):
                raise ConcatTypeError(
                    format_occurs_error(self, subtype),
                    is_occurs_check_fail=True,
                    rigid_variables=rigid_variables,
                )
            return Substitutions([(self, subtype)])
        raise ConcatTypeError(
            format_subtyping_error(context, subtype, self),
            is_occurs_check_fail=False,
            rigid_variables=rigid_variables,
        )


class BoundVariable(Variable):
    def __init__(self, kind: 'Kind') -> None:
        super().__init__()
        self._kind = kind

    @property
    def kind(self) -> 'Kind':
        return self._kind

    @_constrain_on_whnf
    def constrain_and_bind_variables(
        self, context, supertype, rigid_variables, subtyping_assumptions
    ) -> None:
        if (
            self._type_id == supertype._type_id
            or (
                self.kind >= IndividualKind
                and supertype.is_object_type(context)
            )
            or (self, supertype) in subtyping_assumptions
        ):
            return
        if (
            isinstance(supertype, Variable)
            and self.kind <= supertype.kind
            and supertype not in rigid_variables
        ):
            context.substitutions[supertype] = self
            return
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
        rigid_variables: AbstractSet[Variable],
        subtyping_assumptions: Sequence[tuple[Type, Type]],
    ) -> None:
        if (
            self._type_id == supertype._type_id
            or supertype.is_object_type(context)
            or _contains_assumption(subtyping_assumptions, self, supertype)
        ):
            return
        supertype._constrain_as_supertype_of_item_variable(
            context,
            self,
            rigid_variables,
            subtyping_assumptions,
        )

    def _constrain_as_supertype_of_stack_effect(
        self,
        context: TypeChecker,
        subtype: StackEffect,
        rigid_variables: AbstractSet[Variable],
        subtyping_assumptions: Sequence[tuple[Type, Type]],
    ) -> None:
        if not (self.kind >= subtype.kind):
            raise ConcatTypeError(
                format_subkinding_error(subtype, self),
                is_occurs_check_fail=False,
                rigid_variables=rigid_variables,
            )
        if self in rigid_variables:
            raise ConcatTypeError(
                format_rigid_variable_error(self, subtype),
                is_occurs_check_fail=False,
                rigid_variables=rigid_variables,
            )
        if self in subtype.free_type_variables(context):
            raise ConcatTypeError(
                format_occurs_error(self, subtype),
                is_occurs_check_fail=True,
                rigid_variables=rigid_variables,
            )
        context.substitutions[self] = subtype

    def _constrain_as_supertype_of_py_overloaded_type(
        self,
        context: TypeChecker,
        subtype: PythonOverloadedType,
        rigid_variables: AbstractSet[Variable],
        subtyping_assumptions: Sequence[tuple[Type, Type]],
    ) -> None:
        if self not in rigid_variables:
            if self in subtype.free_type_variables(context):
                raise ConcatTypeError(
                    format_occurs_error(self, subtype),
                    is_occurs_check_fail=True,
                    rigid_variables=rigid_variables,
                )
            context.substitutions[self] = subtype
            return
        raise ConcatTypeError(
            format_rigid_variable_error(self, subtype),
            is_occurs_check_fail=False,
            rigid_variables=rigid_variables,
        )

    def _constrain_as_supertype_of_type_sequence(
        self,
        context: TypeChecker,
        subtype: TypeSequence,
        rigid_variables: AbstractSet[Variable],
        subtyping_assumptions: Sequence[tuple[Type, Type]],
    ) -> None:
        raise ConcatTypeError(
            format_subkinding_error(subtype, self),
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
        rigid_variables: AbstractSet[Variable],
        subtyping_assumptions: Sequence[tuple[Type, Type]],
    ) -> None:
        if self._type_id == supertype._type_id:
            return
        if not (supertype.kind <= SequenceKind):
            raise ConcatTypeError(
                '{} must be a sequence type, not {}'.format(self, supertype),
                is_occurs_check_fail=False,
                rigid_variables=rigid_variables,
            )
        supertype._constrain_as_supertype_of_sequence_variable(
            context,
            self,
            rigid_variables,
            subtyping_assumptions,
        )

    def _constrain_as_supertype_of_sequence_variable(
        self,
        context: TypeChecker,
        subtype: SequenceVariable,
        rigid_variables: AbstractSet[Variable],
        subtyping_assumptions: Sequence[tuple[Type, Type]],
    ) -> None:
        if self not in rigid_variables:
            # FIXME: occurs check
            context.substitutions[self] = subtype
            return
        super()._constrain_as_supertype_of_sequence_variable(
            context,
            subtype,
            rigid_variables,
            subtyping_assumptions,
        )

    def _constrain_as_supertype_of_type_sequence(
        self,
        context: TypeChecker,
        subtype: TypeSequence,
        rigid_variables: AbstractSet[Variable],
        subtyping_assumptions: Sequence[tuple[Type, Type]],
    ) -> None:
        if self in subtype.free_type_variables(context):
            raise ConcatTypeError(
                format_occurs_error(self, subtype),
                is_occurs_check_fail=True,
                rigid_variables=rigid_variables,
            )
        if self in rigid_variables:
            raise ConcatTypeError(
                format_rigid_variable_error(self, subtype),
                is_occurs_check_fail=False,
                rigid_variables=rigid_variables,
            )
        context.substitutions[self] = subtype

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

    @_constrain_on_whnf
    def constrain_and_bind_variables(
        self,
        context: TypeChecker,
        supertype,
        rigid_variables,
        subtyping_assumptions,
    ) -> None:
        if self._type_id == supertype._type_id or _contains_assumption(
            subtyping_assumptions, self, supertype
        ):
            return
        # FIXME: Implement occurs check everywhere it should happen.
        if (
            self.kind >= supertype.kind
            and self not in rigid_variables
            and self not in supertype.free_type_variables()
        ):
            context.substitutions[self] = supertype
            return
        if (
            isinstance(supertype, Variable)
            and self.kind <= supertype.kind
            and supertype not in rigid_variables
        ):
            context.substitutions[supertype] = self
            return
        raise ConcatTypeError(
            format_subtyping_error(context, self, supertype),
            is_occurs_check_fail=False,
            rigid_variables=rigid_variables,
        )

    def _constrain_as_supertype_of_type_sequence(
        self,
        context: TypeChecker,
        subtype: TypeSequence,
        rigid_variables: AbstractSet[Variable],
        subtyping_assumptions: Sequence[tuple[Type, Type]],
    ) -> None:
        raise ConcatTypeError(
            format_subtyping_error(context, subtype, self),
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
        return f'GenericType({_iterable_to_str(
            t.force_repr(context) for t in self._type_parameters
        )}, {self._body.force_repr(context)})'

    def apply(
        self, context: TypeChecker, type_arguments: 'TypeArguments'
    ) -> 'Type':
        type_argument_ids = tuple(t._type_id for t in type_arguments)
        if type_argument_ids in self._instantiations:
            return self._instantiations[type_argument_ids]
        expected_kinds = [var.kind for var in self._type_parameters]
        if self.is_variadic:
            type_arguments = [
                VariableArgumentPack.collect_arguments(context, type_arguments)
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
        rigid_variables: AbstractSet[Variable],
        subtyping_assumptions: Sequence[tuple[Type, Type]],
    ) -> None:
        if self is supertype or _contains_assumption(
            subtyping_assumptions, self, supertype
        ):
            return
        # NOTE: Here, we implement subsumption of polytypes, so the kinds don't
        # need to be the same. See concat/poly-subsumption.md for more
        # information.
        supertype._constrain_as_supertype_of_generic(
            context, self, rigid_variables, subtyping_assumptions
        )

    def _constrain_as_supertype_of_generic(
        self,
        context: TypeChecker,
        subtype: GenericType,
        rigid_variables: AbstractSet[Variable],
        subtyping_assumptions: Sequence[tuple[Type, Type]],
    ) -> None:
        if any(
            map(
                lambda t: t in subtype.free_type_variables(context),
                self._type_parameters,
            )
        ):
            raise ConcatTypeError(
                f'Type parameters {
                    self._type_parameters
                } cannot appear free in {subtype}',
                is_occurs_check_fail=True,
                rigid_variables=rigid_variables,
            )
        return subtype.instantiate(context).constrain_and_bind_variables(
            context,
            self._body,
            rigid_variables | set(self._type_parameters),
            subtyping_assumptions,
        )

    def _constrain_as_supertype_of_type_sequence(
        self,
        context: TypeChecker,
        subtype: TypeSequence,
        rigid_variables: AbstractSet[Variable],
        subtyping_assumptions: Sequence[tuple[Type, Type]],
    ) -> None:
        raise ConcatTypeError(
            format_subkinding_error(subtype, self),
            is_occurs_check_fail=None,
            rigid_variables=rigid_variables,
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

    def force(self, context: TypeChecker) -> Type | None:
        if self._rest is not None:
            if not self._individual_types:
                return self._rest.force_if_possible(context)
            rest = self._rest.force(context)
            if rest is None:
                return None
            return TypeSequence(
                context, [*rest.as_sequence(), *self._individual_types]
            )
        return None

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
        rigid_variables: AbstractSet[Variable],
        subtyping_assumptions: Sequence[tuple[Type, Type]],
    ) -> None:
        """Check that self is a subtype of supertype.

        Free type variables that appear in either type sequence are set to be
        equal to their counterparts in the other sequence so that type
        information can be propagated into calls of named functions.
        """
        if self is supertype or _contains_assumption(
            subtyping_assumptions, self, supertype
        ):
            return

        return supertype._constrain_as_supertype_of_type_sequence(
            context,
            self,
            rigid_variables,
            subtyping_assumptions,
        )

    def _constrain_as_supertype_of_type_sequence(
        self,
        context: TypeChecker,
        subtype: TypeSequence,
        rigid_variables: AbstractSet[Variable],
        subtyping_assumptions: Sequence[tuple[Type, Type]],
    ) -> None:
        if subtype._is_empty():
            # [] <: []
            if self._is_empty():
                return
            # [] <: *a, *a is not rigid
            # --> *a = []
            elif (
                subtype._is_empty()
                and self._rest
                and not self._individual_types
                and self._rest not in rigid_variables
            ):
                subtype.constrain_and_bind_variables(
                    context,
                    self._rest,
                    rigid_variables,
                    subtyping_assumptions,
                )
                return
            # [] <: *a? `t0 `t...
            # error
            else:
                raise StackMismatchError(
                    subtype,
                    self,
                    is_occurs_check_fail=None,
                    rigid_variables=rigid_variables,
                )
        if not subtype._individual_types:
            # *a <: [], *a is not rigid
            # --> *a = []
            if self._is_empty() and subtype._rest not in rigid_variables:
                assert subtype._rest is not None
                subtype._rest.constrain_and_bind_variables(
                    context,
                    self,
                    rigid_variables,
                    subtyping_assumptions,
                )
                return
            # *a <: *a
            if subtype._rest is self._rest and not self._individual_types:
                return
            # *a <: *b? `t..., *a is not rigid, *a is not free in RHS
            # --> *a = RHS
            if (
                subtype._rest
                and subtype._rest not in rigid_variables
                and subtype._rest not in self.free_type_variables(context)
            ):
                subtype._rest.constrain_and_bind_variables(
                    context,
                    self,
                    rigid_variables,
                    subtyping_assumptions,
                )
                return
        # *a? `t... `t_n <: []
        # error
        if self._is_empty():
            raise StackMismatchError(
                subtype,
                self,
                is_occurs_check_fail=None,
                rigid_variables=rigid_variables,
            )
        # *a? `t... `t_n <: *b, *b is not rigid, *b is not free in LHS
        # --> *b = LHS
        elif (
            not self._individual_types
            and self._rest
            and self._rest not in subtype.free_type_variables(context)
            and self._rest not in rigid_variables
        ):
            subtype.constrain_and_bind_variables(
                context,
                self._rest,
                rigid_variables,
                subtyping_assumptions,
            )
            return
        # `t_n <: `s_m  *a? `t... <: *b? `s...
        #   ---
        # *a? `t... `t_n <: *b? `s... `s_m
        elif self._individual_types:
            subtype._individual_types[-1].constrain_and_bind_variables(
                context,
                self._individual_types[-1],
                rigid_variables,
                subtyping_assumptions,
            )
            try:
                subtype.index(context, slice(-1)).constrain_and_bind_variables(
                    context,
                    self.index(context, slice(-1)),
                    rigid_variables,
                    subtyping_assumptions,
                )
                return
            except StackMismatchError as e:
                # TODO: Add info about occurs check and rigid
                # variables.
                raise StackMismatchError(
                    subtype,
                    self,
                    e.is_occurs_check_fail,
                    rigid_variables,
                )
        else:
            raise StackMismatchError(
                subtype,
                self,
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

    # FIXME: This conflicts with `ty.force(...) or ty` pattern
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

    @_whnf_self
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
        context = current_context.get()
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
        rigid_variables: AbstractSet[Variable],
        subtyping_assumptions: Sequence[tuple[Type, Type]],
    ) -> None:
        if (
            self is supertype
            or _contains_assumption(subtyping_assumptions, self, supertype)
            or supertype.is_object_type(context)
        ):
            return

        supertype._constrain_as_supertype_of_stack_effect(
            context, self, rigid_variables, subtyping_assumptions
        )

    def _constrain_as_supertype_of_stack_effect(
        self,
        context: TypeChecker,
        subtype: StackEffect,
        rigid_variables: AbstractSet[Variable],
        subtyping_assumptions: Sequence[tuple[Type, Type]],
    ) -> None:
        # Remember that the input should be contravariant!
        self.input.constrain_and_bind_variables(
            context, subtype.input, rigid_variables, subtyping_assumptions
        )
        subtype.output.constrain_and_bind_variables(
            context,
            self.output,
            rigid_variables,
            subtyping_assumptions,
        )

    def _constrain_as_supertype_of_object_type(
        self,
        context: TypeChecker,
        subtype: ObjectType,
        rigid_variables: AbstractSet[Variable],
        subtyping_assumptions: Sequence[tuple[Type, Type]],
    ) -> None:
        subtype.get_type_of_attribute(
            context,
            '__call__',
        ).constrain_and_bind_variables(
            context,
            self,
            rigid_variables,
            subtyping_assumptions,
        )

    def _constrain_as_supertype_of_type_sequence(
        self,
        context: TypeChecker,
        subtype: TypeSequence,
        rigid_variables: AbstractSet[Variable],
        subtyping_assumptions: Sequence[tuple[Type, Type]],
    ) -> None:
        raise ConcatTypeError(
            format_subtyping_error(context, subtype, self),
            is_occurs_check_fail=None,
            rigid_variables=rigid_variables,
        )

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
        return (
            f'StackEffect({self.input.force_repr(context)}, '
            f' {self.output.force_repr(context)})'
        )

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

    def bind(self, context: TypeChecker | None = None) -> 'StackEffect':
        context = context or current_context.get()
        return StackEffect(self.input.index(context, slice(-1)), self.output)


# QUESTION: Do I use this?
class QuotationType(StackEffect):
    def __init__(self, fun_type: StackEffect) -> None:
        super().__init__(fun_type.input, fun_type.output)

    @_constrain_on_whnf
    def constrain_and_bind_variables(
        self,
        context: TypeChecker,
        supertype: Type,
        rigid_variables: AbstractSet[Variable],
        subtyping_assumptions: Sequence[tuple[Type, Type]],
    ) -> None:
        try:
            with context.substitutions.push():
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
                quotation_iterable_type.constrain_and_bind_variables(
                    context, supertype, rigid_variables, subtyping_assumptions
                )
                context.substitutions.commit()
        except ConcatTypeError:
            return super().constrain_and_bind_variables(
                context, supertype, rigid_variables, subtyping_assumptions
            )

    def force_substitution(
        self, context: TypeChecker, sub: Substitutions
    ) -> 'QuotationType':
        return QuotationType(super().force_substitution(context, sub))

    def __repr__(self) -> str:
        return f'QuotationType({StackEffect(self.input, self.output)!r})'

    def force_repr(self, context: TypeChecker) -> str:
        return f'QuotationType({
            StackEffect(self.input, self.output).force_repr(context)
        })'


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
        return f'Brand({self._user_name!r}, {self.kind!r}, {
            self._superbrands!r
        })@{id(self)}'

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
        if not (self.free_type_variables(context) & sub.keys()):
            return self
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

    @_constrain_on_whnf
    def constrain_and_bind_variables(
        self,
        context: TypeChecker,
        supertype,
        rigid_variables,
        subtyping_assumptions,
    ) -> None:
        _logger.debug('{} <:? {}', self, supertype)
        if (
            self._type_id == supertype._type_id
            or _contains_assumption(subtyping_assumptions, self, supertype)
            or supertype.is_object_type(context)
        ):
            return
        return supertype._constrain_as_supertype_of_nominal_type(
            context,
            self,
            rigid_variables,
            subtyping_assumptions,
        )

    def _constrain_as_supertype_of_nominal_type(
        self,
        context: TypeChecker,
        subtype: NominalType,
        rigid_variables: AbstractSet[Variable],
        subtyping_assumptions: Sequence[tuple[Type, Type]],
    ) -> None:
        if subtype._brand.is_subrand_of(context, self._brand):
            return
        raise ConcatTypeError(
            format_subtyping_error(context, subtype, self),
            is_occurs_check_fail=None,
            rigid_variables=rigid_variables,
        )

    def _constrain_as_supertype_of_type_sequence(
        self,
        context: TypeChecker,
        subtype: TypeSequence,
        rigid_variables: AbstractSet[Variable],
        subtyping_assumptions: Sequence[tuple[Type, Type]],
    ) -> NoReturn:
        raise ConcatTypeError(
            format_subkinding_error(subtype, self),
            is_occurs_check_fail=False,
            rigid_variables=rigid_variables,
        )

    def _constrain_as_supertype_of_object_type(
        self,
        context: TypeChecker,
        subtype: ObjectType,
        rigid_variables: AbstractSet[Variable],
        subtyping_assumptions: Sequence[tuple[Type, Type]],
    ) -> NoReturn:
        raise ConcatTypeError(
            f'{format_subtyping_error(context, subtype, self)}, {
                format_not_a_nominal_type_error(subtype)
            }',
            is_occurs_check_fail=False,
            rigid_variables=rigid_variables,
        )

    @property
    def kind(self) -> 'Kind':
        return self._ty.kind

    def brand(self, _context: TypeChecker) -> Brand:
        return self._brand

    def to_user_string(self, _context: TypeChecker) -> str:
        return self._brand.to_user_string()

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
            if (
                t.force_if_possible(context)._type_id
                == context.no_return_type._type_id
            ):
                return context.no_return_type
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

    @_constrain_on_whnf
    def constrain_and_bind_variables(
        self,
        context: TypeChecker,
        supertype: Type,
        rigid_variables: AbstractSet[Variable],
        subtyping_assumptions: Sequence[tuple[Type, Type]],
    ) -> None:
        _logger.debug('{} <:? {}', self, supertype)
        # every object type is a subtype of object_type
        if (
            self._type_id == supertype._type_id
            or supertype.is_object_type(context)
            or _contains_assumption(subtyping_assumptions, self, supertype)
        ):
            return
        return supertype._constrain_as_supertype_of_object_type(
            context,
            self,
            rigid_variables,
            subtyping_assumptions,
        )

    def _constrain_as_supertype_of_object_type(
        self,
        context: TypeChecker,
        subtype: ObjectType,
        rigid_variables: AbstractSet[Variable],
        subtyping_assumptions: Sequence[tuple[Type, Type]],
    ) -> None:
        for name in self._attributes:
            ty = subtype.get_type_of_attribute(context, name)
            ty.constrain_and_bind_variables(
                context,
                self.get_type_of_attribute(context, name),
                rigid_variables,
                subtyping_assumptions,
            )

    def __constrain_as_supertype_of_py_function_or_overloaded_type(
        self,
        context: TypeChecker,
        subtype: PythonOverloadedType | PythonFunctionType,
        rigid_variables: AbstractSet[Variable],
        subtyping_assumptions: Sequence[tuple[Type, Type]],
    ) -> None:
        for attr in self.attributes(context):
            subtype_attr_type = subtype.get_type_of_attribute(context, attr)
            supertype_attr_type = self.get_type_of_attribute(context, attr)
            subtype_attr_type.constrain_and_bind_variables(
                context,
                supertype_attr_type,
                rigid_variables,
                subtyping_assumptions,
            )

    _constrain_as_supertype_of_py_function_type = (
        __constrain_as_supertype_of_py_function_or_overloaded_type
    )

    _constrain_as_supertype_of_py_overloaded_type = (
        __constrain_as_supertype_of_py_function_or_overloaded_type
    )

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

    @_constrain_on_whnf
    def constrain_and_bind_variables(
        self,
        context: TypeChecker,
        supertype,
        rigid_variables,
        subtyping_assumptions,
    ) -> None:
        if self._type_id == supertype._type_id or _contains_assumption(
            subtyping_assumptions, self, supertype
        ):
            return
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
        for subty, superty in zip(self._types, supertype._types):
            subty.constrain_and_bind_variables(
                context,
                superty,
                rigid_variables,
                subtyping_assumptions,
            )

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
        return f'({','.join(t.to_user_string(context) for t in self._types)})'


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
        if self.kind <= SequenceKind:  # TODO: separate this from `apply`
            return self.force(context).index(context, x)
        return DelayedSubstitution(
            context, self._sub, self._ty.apply(context, x)
        )

    def apply_is_redex(self) -> bool:
        return True

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

    @_constrain_on_whnf
    def constrain_and_bind_variables(
        self, context, supertype, rigid_variables, subtyping_assumptions
    ) -> NoReturn:
        raise AssertionError('DelayedSubstitution is never whnf')

    def _constrain_as_supertype_of_type_sequence(
        self, context, subtype, rigid_variables, subtyping_assumptions
    ) -> NoReturn:
        raise AssertionError('DelayedSubstitution is never whnf')

    @property
    def kind(self) -> Kind:
        return self._ty.kind

    def force(self, context: TypeChecker) -> Type:
        if not self._forced:
            self._forced = self._ty.force_substitution(
                context, self._sub
            ).force_if_possible(context)
            assert not isinstance(
                self._forced, DelayedSubstitution
            ), f'{self._ty!r}, {self._forced}'
        return self._forced


class VariableArgumentPack(Type):
    """List of types passed as an argument in a variable-length argument \
    position."""

    def __init__(self, types: Sequence[Type]) -> None:
        super().__init__()
        self._types = types

    @_whnf_self
    def to_user_string(self, _context: TypeChecker) -> str:
        return f'variable-length arguments {
            ', '.join(str(t) for t in self._types)
        }'

    def __repr__(self) -> str:
        return f'VariableArgumentPack({self._types!r})'

    def force(self, context: TypeChecker) -> Type | None:
        if len(self._types) == 1 and self._types[
            0
        ].kind <= VariableArgumentKind(TopKind):
            return self._types[0].force(context)
        return None

    @_whnf_self
    def force_repr(self, context: TypeChecker) -> str:
        return f'VariableArgumentPack({
            _iterable_to_str(t.force_repr(context) for t in self._types)
        })'

    @property
    def arguments(self) -> Sequence[Type]:
        return self._types

    @classmethod
    def collect_arguments(
        cls, context: TypeChecker, args: Iterable[Type]
    ) -> VariableArgumentPack:
        flattened_args: list[Type] = []
        for arg in args:
            if arg.kind <= VariableArgumentKind(TopKind):
                flattened_args += arg.arguments
                continue
            flattened_args.append(arg)
        return VariableArgumentPack(flattened_args)

    @_constrain_on_whnf
    def constrain_and_bind_variables(
        self,
        context: TypeChecker,
        supertype,
        rigid_variables,
        subtyping_assumptions,
    ) -> None:
        if self._type_id == supertype._type_id or _contains_assumption(
            subtyping_assumptions, self, supertype
        ):
            return
        if not (self.kind <= supertype.kind):
            raise ConcatTypeError(
                format_subkinding_error(self, supertype),
                is_occurs_check_fail=None,
                rigid_variables=rigid_variables,
            )
        return supertype._constrain_as_supertype_of_variable_argument_pack(
            context,
            self,
            rigid_variables,
            subtyping_assumptions,
        )

    def _constrain_as_supertype_of_variable_argument_pack(
        self,
        context: TypeChecker,
        subtype: VariableArgumentPack,
        rigid_variables: AbstractSet[Variable],
        subtyping_assumptions: Sequence[tuple[Type, Type]],
    ) -> None:
        if len(subtype._types) != len(self._types):
            raise ConcatTypeError(
                format_subtyping_error(context, subtype, self),
                is_occurs_check_fail=False,
                rigid_variables=rigid_variables,
            )
        for subty, superty in zip(subtype._types, self._types):
            subty.constrain_and_bind_variables(
                context,
                superty,
                rigid_variables,
                subtyping_assumptions,
            )

    def _constrain_as_supertype_of_type_sequence(
        self,
        context: TypeChecker,
        subtype: TypeSequence,
        rigid_variables: AbstractSet[Variable],
        subtyping_assumptions: Sequence[tuple[Type, Type]],
    ) -> NoReturn:
        raise ConcatTypeError(
            format_subkinding_error(subtype, self),
            is_occurs_check_fail=None,
            rigid_variables=rigid_variables,
        )

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

    # FIXME: Should be method on kinds
    @staticmethod
    def _underlying_kind(kind: Kind) -> Kind:
        if isinstance(kind, VariableArgumentKind):
            return kind._argument_kind
        return kind


# QUESTION: Should this exist, or should I use ObjectType?
class ClassType(ObjectType):
    """The representation of types of classes.

    This is based to some degree on "Design and Evaluation of Gradual Typing
    for Python" (Vitousek et al. 2014)."""

    @_constrain_on_whnf
    def constrain_and_bind_variables(
        self,
        context: TypeChecker,
        supertype: Type,
        rigid_variables: AbstractSet[Variable],
        subtyping_assumptions: Sequence[tuple[Type, Type]],
    ) -> None:
        if (
            not supertype.has_attribute(context, '__call__')
            or '__init__' not in self._attributes
        ):
            super().constrain_and_bind_variables(
                context, supertype, rigid_variables, subtyping_assumptions
            )
            return
        init = self.get_type_of_attribute(context, '__init__')
        # FIXME: Use constraint to allow more kinds of type rep
        while not isinstance(init, (StackEffect, PythonFunctionType)):
            init = init.get_type_of_attribute(context, '__call__')
            init = init.force_if_possible(context)
        bound_init = init.bind()
        bound_init.constrain_and_bind_variables(
            context,
            supertype.get_type_of_attribute(context, '__call__'),
            rigid_variables,
            [*subtyping_assumptions, (self, supertype)],
        )


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
        # HACK: Sequence variables are introduced by the type sequence AST
        # nodes
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

    def _free_type_variables(
        self, context: TypeChecker | None = None
    ) -> InsertionOrderedSet[Variable]:
        context = context or current_context.get()
        ftv = self.input.free_type_variables(context)
        ftv |= self.output.free_type_variables(context)
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

    def force_repr(self, context: TypeChecker | None = None) -> str:
        context = context or current_context.get()
        return (
            f'PythonFunctionType(inputs={self.input.force_repr(context)}, '
            f'output={self.output.force_repr(context)})'
        )

    def to_user_string(self, _context: TypeChecker | None) -> str:
        return f'py_function_type[{self.input}, {self.output}]'

    def attributes(
        self, context: TypeChecker | None = None
    ) -> Mapping[str, Type]:
        context = context or current_context.get()
        return {**super().attributes(context), '__call__': self}

    def force_substitution(
        self, context: TypeChecker | None, sub: Substitutions
    ) -> 'PythonFunctionType':
        context = context or current_context.get()
        inp = self.input.apply_substitution(context, sub)
        out = self.output.apply_substitution(context, sub)
        return PythonFunctionType(context, inputs=inp, output=out)

    @property
    def input(self) -> Type:
        return self._type_arguments[0]

    @property
    def output(self) -> Type:
        return self._type_arguments[1]

    def bind(self) -> 'PythonFunctionType':
        context = current_context.get()
        inputs = self.input.index(context, slice(1, None))
        output = self.output
        return PythonFunctionType(
            context,
            inputs=inputs,
            output=output,
        )

    @_constrain_on_whnf
    def constrain_and_bind_variables(
        self,
        context: TypeChecker,
        supertype: Type,
        rigid_variables: AbstractSet[Variable],
        subtyping_assumptions: Sequence[tuple[Type, Type]],
    ) -> None:
        if (
            self._type_id == supertype._type_id
            or supertype.is_object_type(context)
            or _contains_assumption(subtyping_assumptions, self, supertype)
        ):
            return
        if not (self.kind <= supertype.kind):
            raise ConcatTypeError(
                format_subkinding_error(self, supertype),
                is_occurs_check_fail=None,
                rigid_variables=rigid_variables,
            )
        return supertype._constrain_as_supertype_of_py_function_type(
            context,
            self,
            rigid_variables,
            subtyping_assumptions,
        )

    def _constrain_as_supertype_of_py_function_type(
        self,
        context: TypeChecker,
        subtype: PythonFunctionType,
        rigid_variables: AbstractSet[Variable],
        subtyping_assumptions: Sequence[tuple[Type, Type]],
    ) -> None:
        subtype_input_types = subtype.input
        supertype_input_types = self.input
        supertype_input_types.constrain_and_bind_variables(
            context,
            subtype_input_types,
            rigid_variables,
            subtyping_assumptions,
        )
        subtype.output.constrain_and_bind_variables(
            context,
            self.output,
            rigid_variables,
            subtyping_assumptions,
        )

    def _constrain_as_supertype_of_object_type(
        self,
        context: TypeChecker,
        subtype: ObjectType,
        rigid_variables: AbstractSet[Variable],
        subtyping_assumptions: Sequence[tuple[Type, Type]],
    ) -> None:
        subtype.get_type_of_attribute(
            context,
            '__call__',
        ).constrain_and_bind_variables(
            context,
            self,
            rigid_variables,
            subtyping_assumptions,
        )

    def _constrain_as_supertype_of_py_overloaded_type(
        self,
        context: TypeChecker,
        subtype: PythonOverloadedType,
        rigid_variables: AbstractSet[Variable],
        subtyping_assumptions: Sequence[tuple[Type, Type]],
    ) -> None:
        if (
            subtype._overloads.arguments
            and isinstance(subtype._overloads.arguments[0], Variable)
            and subtype._overloads.arguments[0].kind <= SequenceKind
        ):
            return subtype._overloads.arguments[
                0
            ].constrain_and_bind_variables(
                context,
                VariableArgumentPack([self]),
                rigid_variables,
                subtyping_assumptions,
            )

        # Support overloading the subtype.
        exceptions = []
        for overload in subtype._overloads.arguments:
            if isinstance(
                overload, Variable
            ) and overload.kind <= VariableArgumentKind(TopKind):
                overload.constrain_and_bind_variables(
                    context,
                    VariableArgumentPack([self]),
                    rigid_variables,
                    subtyping_assumptions,
                )
                return
            try:
                overload.constrain_and_bind_variables(
                    context,
                    self,
                    rigid_variables,
                    subtyping_assumptions,
                )
                return
            except ConcatTypeError as e:
                exceptions.append(e)
        raise ConcatTypeError(
            f'no overload of {subtype} is a subtype of {self}',
            any(e.is_occurs_check_fail for e in exceptions),
            rigid_variables,
        ) from ExceptionGroup(
            f'{subtype} is not compatible with {self}', exceptions
        )


class _PythonOverloadedType(IndividualType):
    def __init__(self, overloads: Type) -> None:
        super().__init__()
        _fixed_overloads: List[Type] = []
        context = current_context.get()
        self._overloads: VariableArgumentPack
        for overload in overloads.arguments:
            if isinstance(overload, DelayedSubstitution):
                overload = overload.force(context)
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
            # HACK: Sequence variables are introduced by the type sequence AST
            # nodes
            if (
                isinstance(i, TypeSequence)
                and i
                and i.index(context, 0).kind == SequenceKind
            ):
                i = TypeSequence(context, i.as_sequence()[1:])
            _fixed_overloads.append(PythonFunctionType(context, i, o))
        self._overloads = VariableArgumentPack(_fixed_overloads)

    def apply(
        self, _context: TypeChecker | None, args: Sequence[Type]
    ) -> NoReturn:
        raise ConcatTypeError(
            format_not_generic_type_error(self),
            is_occurs_check_fail=None,
            rigid_variables=None,
        )

    def attributes(
        self, _context: TypeChecker | None = None
    ) -> Mapping[str, 'Type']:
        return {'__call__': self}

    def _free_type_variables(
        self, context: TypeChecker | None = None
    ) -> InsertionOrderedSet['Variable']:
        context = context or current_context.get()
        return self._overloads.free_type_variables(context)

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
        #         sub = t.constrain_and_bind_variables(
        #             context, no_return_type, set(), []
        #         )
        #     except ConcatTypeError:
        #         pass
        #     if set(sub) & t.free_type_variables():
        #         return no_return_type
        #     # FIXME: Should look backwards, but not remove both of pairs of
        #     # isomorphic types.
        #     for s in self._overloads.arguments[i + 1:]:
        #         try:
        #             sub = t.constrain_and_bind_variables(
        #                 context, s, set(), []
        #             )
        #         except ConcatTypeError:
        #             overloads.append(t)
        #             continue
        #         if set(sub) & (
        #             t.free_type_variables() | s.free_type_variables()
        #         ):
        #             overloads.append(t)
        if len(overloads) == 1:
            return overloads[0]
        if any(
            t._type_id == context.no_return_type._type_id for t in overloads
        ):
            return context.no_return_type
        return None

    def force_substitution(
        self, context: TypeChecker | None, sub: Substitutions
    ) -> '_PythonOverloadedType':
        context = context or current_context.get()
        return _PythonOverloadedType(
            self._overloads.apply_substitution(context, sub)
        )

    @_constrain_on_whnf
    def constrain_and_bind_variables(
        self,
        context: TypeChecker,
        supertype: 'Type',
        rigid_variables: AbstractSet[Variable],
        subtyping_assumptions: Sequence[tuple[Type, Type]],
    ) -> None:
        if (
            self is supertype
            or _contains_assumption(subtyping_assumptions, self, supertype)
            or supertype.is_object_type(context)
        ):
            return
        if not (self.kind <= supertype.kind):
            raise ConcatTypeError(
                format_subkinding_error(self, supertype),
                is_occurs_check_fail=None,
                rigid_variables=rigid_variables,
            )
        return supertype._constrain_as_supertype_of_py_overloaded_type(
            context,
            self,
            rigid_variables,
            subtyping_assumptions,
        )

    def _constrain_as_supertype_of_object_type(
        self,
        context: TypeChecker,
        subtype: ObjectType,
        rigid_variables: AbstractSet[Variable],
        subtyping_assumptions: Sequence[tuple[Type, Type]],
    ) -> None:
        if self.overloads:
            subtype.get_type_of_attribute(
                context,
                '__call__',
            ).constrain_and_bind_variables(
                context,
                self,
                rigid_variables,
                subtyping_assumptions,
            )

    def _constrain_as_supertype_of_py_overloaded_type(
        self,
        context: TypeChecker,
        subtype: PythonOverloadedType,
        rigid_variables: AbstractSet[Variable],
        subtyping_assumptions: Sequence[tuple[Type, Type]],
    ) -> None:
        # TODO: unsure what to do here
        raise NotImplementedError

    def to_user_string(self, context: TypeChecker) -> str:
        return f'py_overloaded[{
            ', '.join(str(t) for t in self._overloads.arguments)
        }]'

    def __repr__(self) -> str:
        return f'_PythonOverloadedType({self._overloads!r})'

    def force_repr(self, context: TypeChecker) -> str:
        return f'_PythonOverloadedType({self._overloads.force_repr(context)})'

    @property
    def overloads(self) -> Sequence[Type]:
        return self._overloads.arguments


# TODO: Do an actual rename
PythonOverloadedType = _PythonOverloadedType


class _NoReturnType(IndividualType):
    def constrain_and_bind_variables(
        self,
        context: TypeChecker,
        supertype,
        rigid_variables,
        subtyping_assumptions,
    ) -> None:
        pass

    def _constrain_as_supertype_of_object_type(
        self,
        context: TypeChecker,
        subtype: ObjectType,
        rigid_variables: AbstractSet[Variable],
        subtyping_assumptions: Sequence[tuple[Type, Type]],
    ) -> NoReturn:
        raise ConcatTypeError(
            format_subtyping_error(context, subtype, self),
            is_occurs_check_fail=False,
            rigid_variables=rigid_variables,
        )

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
            type_argument.force_if_possible(context)
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

    @_constrain_on_whnf
    def constrain_and_bind_variables(
        self,
        context: TypeChecker,
        supertype: Type,
        rigid_variables,
        subtyping_assumptions,
    ) -> None:
        if (
            self._type_id == supertype._type_id
            or _contains_assumption(subtyping_assumptions, self, supertype)
            or supertype.is_object_type(context)
        ):
            return
        if not (self.kind <= supertype.kind):
            raise ConcatTypeError(
                format_subkinding_error(self, supertype),
                is_occurs_check_fail=None,
                rigid_variables=rigid_variables,
            )
        return supertype._constrain_as_supertype_of_optional_type(
            context,
            self,
            rigid_variables,
            subtyping_assumptions,
        )

    def _constrain_as_supertype_of_item_variable(
        self,
        context: TypeChecker,
        subtype: ItemVariable,
        rigid_variables: AbstractSet[Variable],
        subtyping_assumptions: Sequence[tuple[Type, Type]],
    ) -> None:
        try:
            with context.substitutions.push():
                subtype.constrain_and_bind_variables(
                    context,
                    self.type_arguments[0],
                    rigid_variables,
                    subtyping_assumptions,
                )
                context.substitutions.commit()
            return
        except ConcatTypeError:
            return subtype.constrain_and_bind_variables(
                context,
                context.none_type,
                rigid_variables,
                subtyping_assumptions,
            )

    # A special case for better results (I think)
    def _constrain_as_supertype_of_optional_type(
        self,
        context: TypeChecker,
        subtype: OptionalType,
        rigid_variables: AbstractSet[Variable],
        subtyping_assumptions: Sequence[tuple[Type, Type]],
    ) -> None:
        return subtype._type_argument.constrain_and_bind_variables(
            context,
            self._type_argument,
            rigid_variables,
            subtyping_assumptions,
        )

    def __constrain_param_as_supertype(
        self,
        context: TypeChecker,
        subtype: Type,
        rigid_variables: AbstractSet[Variable],
        subtyping_assumptions: Sequence[tuple[Type, Type]],
    ) -> None:
        subtype.constrain_and_bind_variables(
            context,
            self.type_arguments[0],
            rigid_variables,
            subtyping_assumptions,
        )

    _constrain_as_supertype_of_object_type = __constrain_param_as_supertype

    _constrain_as_supertype_of_py_function_type = (
        __constrain_param_as_supertype
    )

    _constrain_as_supertype_of_stack_effect = __constrain_param_as_supertype

    def _constrain_as_supertype_of_nominal_type(
        self,
        context: TypeChecker,
        subtype: NominalType,
        rigid_variables: AbstractSet[Variable],
        subtyping_assumptions: Sequence[tuple[Type, Type]],
    ) -> None:
        try:
            with context.substitutions.push():
                subtype.constrain_and_bind_variables(
                    context,
                    context.none_type,
                    rigid_variables,
                    subtyping_assumptions,
                )
                context.substitutions.commit()
        except ConcatTypeError:
            return subtype.constrain_and_bind_variables(
                context,
                self.type_arguments[0],
                rigid_variables,
                subtyping_assumptions,
            )

    _constrain_as_supertype_of_py_overloaded_type = (
        __constrain_param_as_supertype
    )

    def force_substitution(
        self, context: TypeChecker, sub: Substitutions
    ) -> '_OptionalType':
        return _OptionalType(
            self._type_argument.apply_substitution(context, sub)
        )

    @property
    def type_arguments(self) -> Sequence[Type]:
        return [self._type_argument]


# TODO: Do an actual rename
NoReturnType = _NoReturnType
OptionalType = _OptionalType


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
        return f'Generic[{
            ', '.join(map(str, self.parameter_kinds))
        }, {self.result_kind}]'

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
        return self._body.force_if_possible(context)

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

    def _constrain_as_supertype_of_optional_type(
        self,
        context: TypeChecker,
        subtype: OptionalType,
        rigid_variables: AbstractSet[Variable],
        subtyping_assumptions: Sequence[tuple[Type, Type]],
    ) -> None:
        return subtype.constrain_and_bind_variables(
            context,
            self.unroll(context),
            rigid_variables,
            [*subtyping_assumptions, (subtype, self)],
        )

    def _constrain_as_supertype_of_object_type(
        self,
        context: TypeChecker,
        subtype: ObjectType,
        rigid_variables: AbstractSet[Variable],
        subtyping_assumptions: Sequence[tuple[Type, Type]],
    ) -> None:
        unrolled = self.unroll(context)
        subtype.constrain_and_bind_variables(
            context,
            unrolled,
            rigid_variables,
            [*subtyping_assumptions, (subtype, self)],
        )

    def _constrain_as_supertype_of_nominal_type(
        self,
        context: TypeChecker,
        subtype: NominalType,
        rigid_variables: AbstractSet[Variable],
        subtyping_assumptions: Sequence[tuple[Type, Type]],
    ) -> None:
        return subtype.constrain_and_bind_variables(
            context,
            self.unroll(context),
            rigid_variables,
            [*subtyping_assumptions, (subtype, self)],
        )

    @_constrain_on_whnf
    def constrain_and_bind_variables(
        self,
        context: TypeChecker,
        supertype: Type,
        rigid_variables,
        subtyping_assumptions,
    ) -> None:
        _logger.debug('{} <:? {}', self, supertype)
        if (
            self._type_id == supertype._type_id
            or supertype.is_object_type(context)
            or _contains_assumption(subtyping_assumptions, self, supertype)
        ):
            return
        return supertype._constrain_as_supertype_of_fixpoint(
            context, self, rigid_variables, subtyping_assumptions
        )

    def _constrain_as_supertype_of_fixpoint(
        self,
        context: TypeChecker,
        subtype: Fix,
        rigid_variables: AbstractSet[Variable],
        subtyping_assumptions: Sequence[tuple[Type, Type]],
    ) -> None:
        unrolled = self.unroll(context)
        subtype.unroll(context).constrain_and_bind_variables(
            context,
            unrolled,
            rigid_variables,
            [*subtyping_assumptions, (subtype, self)],
        )

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

    def force_project(self, i: int) -> Type:
        context = current_context.get()
        return self.unroll(context).project(context, i)

    def brand(self, context: TypeChecker | None = None) -> Brand:
        context = context or current_context.get()
        return self._body.brand(context)


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
