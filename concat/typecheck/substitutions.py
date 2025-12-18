"""Substitution representation and operations."""

from __future__ import annotations

from contextlib import contextmanager
from typing import (
    TYPE_CHECKING,
    Any,
    Iterable,
    Iterator,
    List,
    Mapping,
    Set,
    Tuple,
    Union,
)

from concat.typecheck.errors import format_substitution_kind_error

# circular imports
if TYPE_CHECKING:
    from concat.typecheck import TypeChecker
    from concat.typecheck.types import Type, Variable


# TODO: Use weak dicts


class MutableSubstitutions(Mapping['Variable', 'Type']):
    """A substitution that can be modified.

    In GHC, unification vars hold a mutable ref, and that ref is filled with
    the solution when the var is unified with another type. See:

    - https://gitlab.haskell.org/ghc/ghc/-/blob/fc1d7f7966f56bbe5efaf2796c430dbe526b834b/compiler/GHC/Tc/Utils/TcType.hs#L653

    Since I have backtracking, I need to be able to undo these assignments, so
    I use this data structure as a side table.

    If this doesn't perform well, consider using a persistent union-find data
    structure."""

    def __init__(
        self,
        sub: Union[
            Iterable[Tuple[Variable, Type]],
            Mapping[Variable, Type],
            None,
        ] = None,
    ) -> None:
        self._subs = [{} if sub is None else dict(sub)]
        self._commit_flags: list[bool] = []

    @contextmanager
    def push(self) -> Iterator[Mapping[Variable, Type]]:
        sub: dict[Variable, Type] = {}
        self._subs.append(sub)
        self._commit_flags.append(False)
        yield sub
        if not self._commit_flags.pop():
            self._subs.pop()

    def commit(self) -> None:
        self._commit_flags[-1] = True

    def __getitem__(self, k: Variable) -> Type:
        for sub in self._subs:
            if k in sub:
                return sub[k]
        raise KeyError(k)

    def __setitem__(self, k: Variable, v: Type) -> None:
        assert k not in self
        self._subs[-1][k] = v

    def __iter__(self) -> Iterator[Variable]:
        for sub in self._subs:
            yield from sub

    def __len__(self) -> int:
        return sum(len(sub) for sub in self._subs)


class Substitutions(Mapping['Variable', 'Type']):
    """Substitutions of type variables with types."""

    __next_id = 0

    def __init__(
        self,
        sub: Union[
            Iterable[Tuple['Variable', 'Type']],
            Mapping['Variable', 'Type'],
            None,
        ] = None,
    ) -> None:
        self._sub = {} if sub is None else dict(sub)
        self.id = Substitutions.__next_id
        Substitutions.__next_id += 1
        for variable, ty in self._sub.items():
            if not (variable.kind >= ty.kind):
                raise TypeError(format_substitution_kind_error(variable, ty))
        # NOTE: Substitutable types should manage their own caching [SUBCACHE]

        # innermost first
        self.subtyping_provenance: List[Any] = []

    def add_subtyping_provenance(
        self, subtyping_query: Tuple['Type', 'Type']
    ) -> None:
        self.subtyping_provenance.append(subtyping_query)

    def __getitem__(self, var: 'Variable') -> 'Type':
        return self._sub[var]

    def __iter__(self) -> Iterator['Variable']:
        return iter(self._sub)

    def __len__(self) -> int:
        return len(self._sub)

    def __bool__(self) -> bool:
        return bool(self._sub)

    def _dom(self) -> Set['Variable']:
        return {*self}

    def __str__(self) -> str:
        return (
            f'{{{', '.join(map(lambda i: f'{i[0]}: {i[1]}', self.items()))}}}'
        )

    def __repr__(self) -> str:
        return f'Substitutions({self._sub!r})'

    def apply_substitution(
        self,
        context: TypeChecker,
        sub: 'Substitutions',
    ) -> 'Substitutions':
        new_sub = Substitutions(
            {
                **sub,
                **{
                    a: i.apply_substitution(context, sub)
                    for a, i in self.items()
                    if a not in sub._dom()
                },
            }
        )
        new_sub.subtyping_provenance = [
            (self.subtyping_provenance, sub.subtyping_provenance)
        ]
        return new_sub

    def __hash__(self) -> int:
        return hash(tuple(self.items()))
