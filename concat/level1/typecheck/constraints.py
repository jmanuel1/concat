from enum import Enum, auto
from typing import TYPE_CHECKING, Iterator, List, Set, Tuple, cast


if TYPE_CHECKING:
    from concat.level1.typecheck.types import (
        IndividualType,
        IndividualVariable,
        Type,
        _Variable,
    )
    from concat.level1.typecheck import Substitutions


class _ConstraintDirection(Enum):
    SUBTYPE = auto()
    SUPERTYPE = auto()

    @staticmethod
    def switch(direction: '_ConstraintDirection'):
        if direction == _ConstraintDirection.SUBTYPE:
            return _ConstraintDirection.SUPERTYPE
        return _ConstraintDirection.SUBTYPE


class _Constraint:
    def __init__(
        self, var: '_Variable', type: 'Type', direction: _ConstraintDirection
    ) -> None:
        self._variable = var
        self._type = type
        self._direction = direction

    def converse(self):
        direction = _ConstraintDirection.switch(self._direction)
        return _Constraint(self._variable, self._type, direction)

    @property
    def variable(self) -> '_Variable':
        return self._variable

    @property
    def type(self) -> 'Type':
        return self._type

    @property
    def direction(self) -> _ConstraintDirection:
        return self._direction

    def __str__(self) -> str:
        if self._direction == _ConstraintDirection.SUBTYPE:
            arrow = '<='
        else:
            arrow = '>='
        return '{} {} {}'.format(self._variable, arrow, self._type)

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, _Constraint):
            return NotImplemented
        self_tuple = self._as_tuple()
        other_tuple = other._as_tuple()
        return self_tuple == other_tuple

    def __hash__(self) -> int:
        return hash(self._as_tuple())

    def _as_tuple(self) -> Tuple['_Variable', 'Type', _ConstraintDirection]:
        return self._variable, self._type, self._direction


class Constraints:
    def __init__(self) -> None:
        self._graph = _ConstraintGraph(self)

    def add(self, subtype: 'Type', supertype: 'Type') -> None:
        from concat.level1.typecheck.types import _Variable

        if isinstance(subtype, _Variable):
            self._graph.add_edge(
                _Constraint(subtype, supertype, _ConstraintDirection.SUBTYPE)
            )
        elif isinstance(supertype, _Variable):
            self._graph.add_edge(
                _Constraint(supertype, subtype, _ConstraintDirection.SUPERTYPE)
            )
        else:
            subtype.constrain(supertype, self)

    def equalities_as_substitutions(self) -> 'Substitutions':
        from concat.level1.typecheck import Substitutions

        sub = Substitutions()
        for constraint in self._list:
            if constraint.converse() in self._list:
                # Applying the new mapping to the substitution should take care
                # of transitive equality for us. More precisely, a variable
                # will eventually be mapped to the last seen type it is equal
                # to. This should not be a problem when e.g. there are
                # constraints var_a <= var_b and var_b <= var_a and you end up
                # with {var_a: var_a} because those variable should be
                # interchangeable anyway. See Substitutions.apply_substitution
                # in concat.level1.typecheck.__init__.py.
                sub = Substitutions({constraint.variable: constraint.type})(
                    sub
                )
        return sub

    def get_supertype_of(self, var: 'IndividualVariable') -> 'IndividualType':
        from concat.level1.typecheck.types import IndividualType, object_type

        # FIXME: We assume there is only one answer.
        for constraint in self._list:
            if (
                constraint.variable is var
                and constraint.direction == _ConstraintDirection.SUBTYPE
            ):
                return cast(IndividualType, constraint.type)
            elif (
                constraint.type is var
                and constraint.direction == _ConstraintDirection.SUPERTYPE
            ):
                return cast(IndividualType, constraint.variable)
        return object_type

    def __str__(self) -> str:
        return '[' + ', '.join(str(c) for c in self._list) + ']'

    @property
    def _list(self) -> List[_Constraint]:
        return list(self._graph.edges)


class _ConstraintGraph:
    """A graph representing constraints on type variables.

    Edges are directed from subtypes to supertypes.
    """

    def __init__(self, parent: Constraints) -> None:
        self._edges: Set[_Constraint] = set()
        self._parent = parent

    def add_edge(self, constraint: _Constraint) -> None:
        # The general idea here is to check all the new paths that are created
        # by adding the constraint to the graph.
        if constraint in self._edges:
            return
        self._edges.add(constraint)
        variable, type = constraint.variable, constraint.type
        if constraint.direction == _ConstraintDirection.SUBTYPE:
            for subtype_of_var in self._types_with_paths_to(variable):
                self._parent.add(subtype_of_var, type)
            for supertype_of_type in self._types_with_paths_from(type):
                self._parent.add(variable, supertype_of_type)
        else:
            for supertype_of_var in self._types_with_paths_from(variable):
                self._parent.add(type, supertype_of_var)
            for subtype_of_type in self._types_with_paths_to(type):
                self._parent.add(subtype_of_type, variable)

    @property
    def edges(self) -> Iterator[_Constraint]:
        return iter(self._edges)

    def _types_with_paths_to(self, type: 'Type') -> Iterator['Type']:
        visited = {type}
        changed = True
        while changed:
            changed = False
            for t in visited.copy():
                for edge in self._edges:
                    if (
                        edge.variable is t
                        and edge.direction == _ConstraintDirection.SUPERTYPE
                    ):
                        if edge.type not in visited:
                            visited.add(edge.type)
                            changed = True
                    elif (
                        edge.type == t
                        and edge.direction == _ConstraintDirection.SUBTYPE
                    ):
                        if edge.variable not in visited:
                            visited.add(edge.variable)
                            changed = True
        return iter(visited)

    def _types_with_paths_from(self, type: 'Type') -> Iterator['Type']:
        visited = {type}
        changed = True
        while changed:
            changed = False
            for t in visited.copy():
                for edge in self._edges:
                    if (
                        edge.variable is t
                        and edge.direction == _ConstraintDirection.SUBTYPE
                    ):
                        if edge.type not in visited:
                            visited.add(edge.type)
                            changed = True
                    elif (
                        edge.type == t
                        and edge.direction == _ConstraintDirection.SUPERTYPE
                    ):
                        if edge.variable not in visited:
                            visited.add(edge.variable)
                            changed = True
        return iter(visited)
