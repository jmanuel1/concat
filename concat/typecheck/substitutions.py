"""Substitution representation and operations."""


from __future__ import annotations
from concat.typecheck.errors import format_substitution_kind_error
from typing import (
    Any,
    Iterable,
    Iterator,
    List,
    Mapping,
    Protocol,
    Set,
    Tuple,
    TYPE_CHECKING,
    TypeVar,
    Union,
)


# circular imports
if TYPE_CHECKING:
    from concat.typecheck.types import Type, Variable


_Result = TypeVar('_Result', covariant=True)


class _Substitutable(Protocol[_Result]):
    def apply_substitution(self, sub: 'Substitutions') -> _Result:
        # empty, abstract protocol method
        pass


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

    def __call__(self, arg: _Substitutable[_Result]) -> _Result:
        result: _Result
        # Previously I tried caching results by the id of the argument. But
        # since the id is the memory address of the object in CPython, another
        # object might have the same id later. I think this was leading to
        # nondeterministic Concat type errors from the type checker.
        # See [SUBCACHE] for why caching is not done here.
        result = arg.apply_substitution(self)
        return result

    def _dom(self) -> Set['Variable']:
        return {*self}

    def __str__(self) -> str:
        return (
            f'{{{', '.join(map(lambda i: f'{i[0]}: {i[1]}', self.items()))}}}'
        )

    def apply_substitution(self, sub: 'Substitutions') -> 'Substitutions':
        new_sub = Substitutions(
            {
                **sub,
                **{a: sub(i) for a, i in self.items() if a not in sub._dom()},
            }
        )
        new_sub.subtyping_provenance = [
            (self.subtyping_provenance, sub.subtyping_provenance)
        ]
        return new_sub

    def __hash__(self) -> int:
        return hash(tuple(self.items()))
