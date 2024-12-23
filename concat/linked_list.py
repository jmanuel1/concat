from typing import (
    Callable,
    Iterable,
    Iterator,
    List,
    Optional,
    Sequence,
    Tuple,
    TypeVar,
    Union,
    overload,
)
from typing_extensions import Never

_T_co = TypeVar('_T_co', covariant=True)
_T = TypeVar('_T')


class LinkedList(Sequence[_T_co]):
    def __init__(
        self, _val: Optional[Tuple[_T_co, 'LinkedList[_T_co]']]
    ) -> None:
        self._val = _val
        self._length: Optional[int] = None

    @classmethod
    def from_iterable(cls, iterable: Iterable[_T_co]) -> 'LinkedList[_T_co]':
        if isinstance(iterable, cls):
            return iterable
        l: LinkedList[_T_co] = cls(None)
        head = l
        for el in iterable:
            next_node = cls(None)
            l._val = (el, next_node)
            l = next_node
        return head

    @overload
    def __getitem__(self, i: int) -> _T_co:
        pass

    @overload
    def __getitem__(self, i: slice) -> 'LinkedList[_T_co]':
        pass

    def __getitem__(
        self, i: Union[slice, int]
    ) -> Union['LinkedList[_T_co]', _T_co]:
        if isinstance(i, slice):
            raise NotImplementedError
        for _ in range(i):
            if self._val is None:
                raise IndexError
            self = self._val[1]
        if self._val is None:
            raise IndexError
        return self._val[0]

    def __len__(self) -> int:
        if self._length is None:
            node = self
            length = 0
            while node._val is not None:
                node = node._val[1]
                length += 1
            self._length = length
        return self._length

    def __add__(self, other: 'LinkedList[_T_co]') -> 'LinkedList[_T_co]':
        if not isinstance(other, LinkedList):
            return NotImplemented
        for el in reversed(list(self)):
            other = LinkedList((el, other))
        return other

    def filter(self, p: Callable[[_T_co], bool]) -> 'LinkedList[_T_co]':
        if self._val is None:
            return self
        # FIXME: Stack safety
        # TODO: Reuse as much of tail as possible
        if p(self._val[0]):
            tail = self._val[1].filter(p)
            return LinkedList((self._val[0], tail))
        return self._val[1].filter(p)

    def _tails(self) -> 'List[LinkedList[_T_co]]':
        res: List[LinkedList[_T_co]] = []
        while self._val is not None:
            res.append(self)
            self = self._val[1]
        return res

    def __iter__(self) -> Iterator[_T_co]:
        while self._val is not None:
            yield self._val[0]
            self = self._val[1]

    def __str__(self) -> str:
        return str(list(self))

    def __repr__(self) -> str:
        return f'LinkedList.from_iterable({list(self)!r})'

    # "supertype defines the argument type as object"
    def __eq__(self, other: object) -> bool:
        if not isinstance(other, LinkedList):
            return NotImplemented
        if len(self) != len(other):
            return False
        for a, b in zip(self, other):
            if a != b:
                return False
        return True


empty_list = LinkedList[Never](None)
