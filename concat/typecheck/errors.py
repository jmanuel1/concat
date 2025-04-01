from __future__ import annotations
import builtins
import concat.parse
import pathlib
from typing import AbstractSet, TYPE_CHECKING


if TYPE_CHECKING:
    import concat.astutils
    from concat.typecheck.types import Kind, Type, TypeSequence, Variable


class StaticAnalysisError(Exception):
    def __init__(self, message: str) -> None:
        self.message = message
        self.location: concat.astutils.Location | None = None
        self.path: pathlib.Path | None = None

    def set_location_if_missing(
        self, location: 'concat.astutils.Location'
    ) -> None:
        if not self.location:
            self.location = location

    def set_path_if_missing(self, path: pathlib.Path) -> None:
        if self.path is None:
            self.path = path

    def __str__(self) -> str:
        return '{} at {}'.format(self.message, self.location)


class TypeError(StaticAnalysisError, builtins.TypeError):
    """Type errors raised by the Concat type checker.

    is_occurs_check_fail is None if it is not applicable to the error (e.g. the
    two sides of a constraint are not variables). rigid_variables is None when
    it's irrelevant (e.g. for an attribute error).
    """

    def __init__(
        self,
        message: str,
        is_occurs_check_fail: bool | None,
        rigid_variables: AbstractSet[Variable] | None,
    ) -> None:
        super().__init__(message)
        self.is_occurs_check_fail = is_occurs_check_fail
        self.rigid_variables = rigid_variables

    def __repr__(self) -> str:
        return f'TypeError({self.message!r}, is_occurs_check_fail={
            self.is_occurs_check_fail!r
        }, rigid_variables={self.rigid_variables!r})'


class NameError(StaticAnalysisError, builtins.NameError):
    def __init__(
        self,
        name: concat.parse.NameWordNode | str,
        location: concat.astutils.Location | None = None,
    ) -> None:
        if isinstance(name, concat.parse.NameWordNode):
            location = name.location
            name = name.value
        super().__init__(f'name {name!r} not previously defined')
        self._name = name
        self.location = location

    def __str__(self) -> str:
        location_info = ''
        if self.location:
            location_info = ' (error at {}:{})'.format(*self.location)
        return self.message + location_info


class AttributeError(TypeError, builtins.AttributeError):
    def __init__(self, type: 'Type', attribute: str) -> None:
        super().__init__(
            'object of type {} does not have attribute {}'.format(
                type, attribute
            ),
            is_occurs_check_fail=None,
            rigid_variables=None,
        )
        self._type = type
        self._attribute = attribute


class StackMismatchError(TypeError):
    def __init__(
        self,
        actual: TypeSequence,
        expected: TypeSequence,
        is_occurs_check_fail: bool | None,
        rigid_variables: AbstractSet[Variable] | None,
    ) -> None:
        super().__init__(
            f'The stack here is {
                actual
            }, but sequence type {expected} was expected',
            is_occurs_check_fail,
            rigid_variables,
        )


class UnhandledNodeTypeError(builtins.NotImplementedError):
    pass


def format_item_type_expected_in_type_sequence_error(ty: Type) -> str:
    return (
        'an item type was expected in this part of a type sequence, got '
        f'{ty}'
    )


def format_wrong_number_of_type_arguments_error(
    expected: int, actual: int
) -> str:
    return (
        f'a generic type expected to receive {expected} arguments, got '
        f'{actual}'
    )


def format_too_many_params_for_variadic_type_error() -> str:
    return 'Only one parameter is allowed for a variadic generic type'


def format_subtyping_error(subtype: Type, supertype: Type) -> str:
    return f'{subtype} cannot be a subtype of {supertype}'


def format_name_reassigned_in_type_sequence_error(name: str) -> str:
    return (
        f'{name} is associated with a type more than once in this sequence '
        'of types'
    )


def format_occurs_error(v: Variable, ty: Type) -> str:
    return (
        f'{v} cannot be a subtype of {ty} because it would form a recursive '
        'type'
    )


def format_not_a_variable_error(name: str) -> str:
    return f'{name} does not refer to a variable'


def format_substitution_kind_error(variable: Variable, ty: Type) -> str:
    return (
        f'{variable} is being substituted by {ty}, which has the wrong kind '
        f'({variable.kind} vs {ty.kind})'
    )


def format_not_generic_type_error(ty: Type) -> str:
    return f'{ty} is not a generic type (has kind {ty.kind})'


def format_generic_type_attributes_error(ty: Type) -> str:
    return f'Generic type {
        ty
    } does not have attributes; maybe you forgot type arguments?'


def format_not_allowed_as_overload_error(ty: Type) -> str:
    return f'{ty} cannot be the type of an overload of a Python function'


def format_sequence_var_must_be_only_arg_of_py_overloaded(
    var: Variable,
) -> str:
    return f'{var} must be the only argument of py_overloaded'


def format_rigid_variable_error(var: Variable, ty: Type) -> str:
    return f'{var} is rigid and cannot be unified with {ty}'


def format_wrong_arg_kind_error(
    head: Type, i: int, arg: Type, param_kind: Kind
):
    return (
        f'Argument {i} of {head} ({arg}), has kind {arg.kind}, but expected '
        f'kind {param_kind}'
    )


def format_decorator_result_kind_error(ty: Type) -> str:
    return f'Decorators should produce something of item kind, got {ty}'


def format_subkinding_error(sub: Type, sup: Type) -> str:
    return (
        f'The kind of {sub} ({sub.kind}) is incompatible with the kind of '
        f'{sup} ({sup.kind})'
    )


def format_expected_item_kinded_variable_error(name: str, ty: Type) -> str:
    return f'{name} is not of item kind (has kind {ty.kind})'


def format_cannot_have_attributes_error(ty: Type) -> str:
    return f'{ty} cannot have attributes'


def format_attributes_unknown_error(ty: Type) -> str:
    return f'The attributes of {ty} are unknown here'


def format_type_tuple_index_out_of_range_error(ty: Type, index: int) -> str:
    return f'Tuple type {ty} does not support index {index}'


def format_not_a_type_tuple_error(ty: Type) -> str:
    return f'{ty} is not a type tuple'


def format_unknown_sequence_type(ty: Type) -> str:
    return f'Not enough info about sequence type {ty} is known'


def format_not_a_nominal_type_error(ty: Type) -> str:
    return f'{ty} is not a nominal type'


def format_must_be_item_type_error(ty: Type) -> str:
    return f'{ty} must be an item type, but has kind {ty.kind}'


def format_cannot_find_module_from_source_dir_error(
    module: str,
    source_dir: pathlib.Path,
) -> str:
    return f'Cannot find module {module} from source directory {source_dir}'


def format_cannot_find_module_path_error(module: str):
    return f'Cannot find path of module {module}'
