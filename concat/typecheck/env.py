"""Typing environments."""


from __future__ import annotations
from collections.abc import Iterator, Mapping
from concat.orderedset import InsertionOrderedSet
from functools import reduce
from operator import or_
from typing import Optional, TYPE_CHECKING


if TYPE_CHECKING:
    # circular imports
    from concat.typecheck.types import Type, Variable

    # type only
    from concat.typecheck.substitutions import Substitutions


class Environment(Mapping[str, 'Type']):
    def __init__(self, env: Optional[Mapping[str, Type]] = None) -> None:
        self._env = env or dict()
        self._sub_cache = dict[int, Environment]()

    def apply_substitution(self, sub: 'Substitutions') -> 'Environment':
        # because of caching, environments are immutable structures
        if sub.id not in self._sub_cache:
            self._sub_cache[sub.id] = Environment(
                {name: sub(t) for name, t in self.items()}
            )
        return self._sub_cache[sub.id]

    def free_type_variables(self) -> 'InsertionOrderedSet[Variable]':
        return reduce(
            or_,
            map(lambda t: t.free_type_variables(), self.values()),
            InsertionOrderedSet([]),
        )

    def __getitem__(self, name: str) -> Type:
        return self._env[name]

    def __iter__(self) -> Iterator[str]:
        return iter(self._env)

    def __len__(self) -> int:
        return len(self._env)

    def __or__(self, other: Mapping[str, Type]) -> Environment:
        return Environment({**self, **other})
