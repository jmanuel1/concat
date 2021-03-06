from enum import Enum, auto
from typing import TYPE_CHECKING, List


if TYPE_CHECKING:
    from concat.level1.typecheck.types import Type, _Variable


class _ConstraintDirection(Enum):
    SUBTYPE = auto
    SUPERTYPE = auto


class _Constraint:
    def __init__(self, var: '_Variable', type: 'Type', direction: _ConstraintDirection) -> None:
        self._variable = var
        self._type = type
        self._direction = direction

    def __str__(self) -> str:
        arrow = '<=' if self._direction == _ConstraintDirection.SUBTYPE else '>='
        return '{} {} {}'.format(self._variable, arrow, self._type)


class Constraints:
    def __init__(self) -> None:
        self._list: List[_Constraint] = []

    def add(self, subtype: 'Type', supertype: 'Type') -> None:
        from concat.level1.typecheck.types import _Variable
        if isinstance(subtype, _Variable):
            self._list.append(_Constraint(subtype, supertype, _ConstraintDirection.SUBTYPE))
        elif isinstance(supertype, _Variable):
            self._list.append(_Constraint(supertype, subtype, _ConstraintDirection.SUPERTYPE))
        else:
            subtype.constrain(supertype, self)

    def __str__(self) -> str:
        return '[' + ' '.join(str(c) for c in self._list) + ']'
