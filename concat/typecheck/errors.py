from __future__ import annotations
import builtins
import concat.parse
import pathlib
from typing import Optional, Union, TYPE_CHECKING


if TYPE_CHECKING:
    import concat.astutils
    from concat.typecheck.types import Type, TypeSequence, Variable


class StaticAnalysisError(Exception):
    def __init__(self, message: str) -> None:
        self.message = message
        self.location: Optional['concat.astutils.Location'] = None
        self.path: Optional[pathlib.Path] = None

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
    pass


class NameError(StaticAnalysisError, builtins.NameError):
    def __init__(
        self,
        name: Union['concat.parse.NameWordNode', str],
        location: Optional['concat.astutils.Location'] = None,
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
            )
        )
        self._type = type
        self._attribute = attribute


class StackMismatchError(TypeError):
    def __init__(
        self, actual: 'TypeSequence', expected: 'TypeSequence'
    ) -> None:
        super().__init__(
            'The stack here is {}, but sequence type {} was expected'.format(
                actual, expected
            )
        )


class UnhandledNodeTypeError(builtins.NotImplementedError):
    pass


def format_item_type_expected_in_type_sequence_error(ty: Type) -> str:
    return (
        'an item type was expected in this part of a type sequence, got '
        f'{ty}'
    )


def format_name_reassigned_in_type_sequence_error(name: str) -> str:
    return (
        f'{name} is associated with a type more than once in this sequence '
        'of types'
    )


def format_not_a_variable_error(name: str) -> str:
    return f'{name} does not refer to a variable'


def format_substitution_kind_error(variable: Variable, ty: Type) -> str:
    return (
        f'{variable} is being substituted by {ty}, which has the wrong kind '
        f'({variable.kind} vs {ty.kind})'
    )
