from itertools import repeat
from typing import AbstractSet, Iterable, Iterator, TypeVar


_T = TypeVar('_T', covariant=True)


class OrderedSet(AbstractSet[_T]):
    def __init__(self, elements: Iterable[_T]) -> None:
        super().__init__()
        # In Python 3.7+, dicts are guaranteed to use insertion order.
        self._dictionary = dict(zip(elements, repeat(None)))

    def __sub__(self, other: object) -> 'OrderedSet[_T]':
        if not isinstance(other, AbstractSet):
            return NotImplemented
        return OrderedSet(
            element for element in self._dictionary if element not in other
        )

    def __or__(self, other: object) -> 'OrderedSet[_T]':
        if not isinstance(other, AbstractSet):
            return NotImplemented
        return OrderedSet([*self, *other])

    def __contains__(self, element: object) -> bool:
        return element in self._dictionary

    def __iter__(self) -> Iterator[_T]:
        return iter(self._dictionary)

    def __len__(self) -> int:
        return len(self._dictionary)
