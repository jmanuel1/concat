"""Typing environments."""

from __future__ import annotations

from collections.abc import Iterator, Mapping
from functools import reduce
from operator import or_
from typing import TYPE_CHECKING, Callable, Optional

from concat.orderedset import InsertionOrderedSet

if TYPE_CHECKING:
    from concat.typecheck import TypeChecker

    # type only
    from concat.typecheck.substitutions import Substitutions

    # circular imports
    from concat.typecheck.types import Type, Variable

    type _FixFormer = Callable[[Environment, Type], Type]


class Environment(Mapping[str, 'Type']):
    """A map from names in a typing context to the types of those names."""

    def __init__(self, env: Optional[Mapping[str, Type]] = None) -> None:
        self._env = env or {}
        self._mutuals: dict[str, _FixFormer] = {}
        self._sub_cache = dict[int, Environment]()

    def apply_substitution(
        self, context: TypeChecker, sub: 'Substitutions'
    ) -> 'Environment':
        # because of caching, environments are immutable structures
        if sub.id not in self._sub_cache:
            if not (set(sub) & self.free_type_variables(context)):
                self._sub_cache[sub.id] = self
            self._sub_cache[sub.id] = Environment(
                {
                    name: t.apply_substitution(context, sub)
                    for name, t in self.items()
                }
            )
            self._sub_cache[sub.id]._mutuals = {
                n: lambda e, t, f=f: f(e, t).apply_substitution(context, sub)
                for n, f in self._mutuals.items()
            }
        return self._sub_cache[sub.id]

    def free_type_variables(
        self, context: TypeChecker
    ) -> 'InsertionOrderedSet[Variable]':
        return reduce(
            or_,
            map(lambda t: t.free_type_variables(context), self.values()),
            InsertionOrderedSet([]),
        )

    def __getitem__(self, name: str) -> Type:
        return self._env[name]

    def __iter__(self) -> Iterator[str]:
        return iter(self._env)

    def __len__(self) -> int:
        return len(self._env)

    def __or__(self, other: Mapping[str, Type]) -> Environment:
        env = Environment({**self, **other})
        env._mutuals = {**self._mutuals}
        if isinstance(other, Environment):
            env._mutuals |= other._mutuals
        return env

    def with_mutuals(
        self, referer: str, fix_former: _FixFormer
    ) -> Environment:
        env = self.copy()
        env._mutuals[referer] = fix_former
        return env

    def copy(self) -> Environment:
        env = Environment(self._env)
        env._mutuals = {**self._mutuals}
        return env

    def get_mutuals(self, referer: str) -> _FixFormer:
        return self._mutuals.get(referer, lambda _, t: t)

    def __str__(self) -> str:
        return f'{{{', '.join(f'{n}: {t}' for n, t in self.items())}}}'

    def __repr__(self) -> str:
        return f'Environment({self._env!r}) <mutuals: {self._mutuals!r}>'
