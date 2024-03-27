from typing import AbstractSet, Any, Iterable, Iterator, Tuple, TypeVar

_T = TypeVar('_T', covariant=True)


class OrderedSet(AbstractSet[_T]):
    def __init__(self, elements: Iterable[_T]) -> None:
        super().__init__()
        self._data = _Tree23.from_iterable(elements)

    def __sub__(self, other: object) -> 'OrderedSet[_T]':
        if not isinstance(other, AbstractSet):
            return NotImplemented
        data = self._data
        for el in other:
            data = data.delete(el)
        return OrderedSet(data)

    def __or__(self, other: object) -> 'OrderedSet[_T]':
        if not isinstance(other, AbstractSet):
            return NotImplemented
        data = self._data
        for el in other:
            data = data.insert(el)
        return OrderedSet(data)

    def __contains__(self, element: object) -> bool:
        return element in self._data

    def __iter__(self) -> Iterator[_T]:
        return iter(self._data)

    def __len__(self) -> int:
        return len(self._data)


class _Tree23Hole:
    pass


class _Tree23:
    """Implementation based on https://www.cs.princeton.edu/~dpw/courses/cos326-12/ass/2-3-trees.pdf.

    Kinds of nodes:
    Leaf: ()
    2-node: (l, X, r)
    3-node: (l, X, m, Y, r)

    Intermediary nodes:
    Kicked up node: ('up', a, w, b)
    Hole node: (__hole, l)"""

    def __init__(self, data: tuple) -> None:
        self._data = data
        if self.is_leaf():
            self.height = 0
        elif self.is_2_node():
            # assert not isinstance(data[0], _Tree23Hole) and not isinstance(
            #     data[2], _Tree23Hole)
            self.height = max(data[0].height, data[2].height) + 1
        elif self.is_3_node():
            # assert not isinstance(data[0], _Tree23Hole) and not isinstance(
            #     data[2], _Tree23Hole) and not isinstance(data[4], _Tree23Hole)
            self.height = (
                max(data[0].height, data[2].height, data[4].height) + 1
            )
        elif self._is_kicked_up_node():
            assert not isinstance(data[2], _Tree23Hole) and not isinstance(
                data[3], _Tree23Hole
            )
            self.height = max(data[1].height, data[3].height)
        elif self._is_hole_node():
            self.height = data[1].height + 1
        else:
            raise ValueError('Invalid 2-3 tree')

    @classmethod
    def from_iterable(cls, i: Iterable) -> '_Tree23':
        if isinstance(i, cls):
            return i
        tree = _leaf_23_tree
        for el in i:
            tree = tree.insert(el)
        return tree

    def search(self, d) -> Tuple[bool, Any]:
        t = self
        while True:
            data = t._data
            if t.is_leaf():
                return (False, None)
            if t.is_2_node():
                p, a, q = data
                if d < a:
                    t = p
                elif d == a:
                    return (True, a)
                else:
                    t = q
            elif t.is_3_node():
                p, a, q, b, r = data
                if d < a:
                    t = p
                elif d == a:
                    return (True, a)
                elif d < b:
                    t = q
                elif d == b:
                    return (True, b)
                else:
                    t = r

    def __iter__(self) -> Iterator:
        if self.is_leaf():
            return
        if self.is_2_node():
            yield from self._data[0]
            yield self._data[1]
            yield from self._data[2]
        if self.is_3_node():
            yield self._data[3]
            yield from self._data[4]

    def __len__(self) -> int:
        if self.is_leaf():
            return 0
        if self.is_2_node():
            return len(self._data[0]) + 1 + len(self._data[2])
        if self.is_3_node():
            return (
                len(self._data[0])
                + 1
                + len(self._data[2])
                + 1
                + len(self._data[4])
            )
        raise ValueError('Invalid 2-3 tree')

    def _insert(self, key) -> '_Tree23':
        data = self._data
        if self.is_leaf():
            return _Tree23(('up', _leaf_23_tree, key, _leaf_23_tree))
        if self.is_2_node():
            p, a, q = data
            # print(key, a)
            if key < a:
                p_ = p._insert(key)
                return _Tree23((p_, a, q))._insert_upwards_phase()
            if key == a:
                return _Tree23((p, key, q))
            q_ = q._insert(key)
            return _Tree23((p, a, q_))._insert_upwards_phase()
        if self.is_3_node():
            l, X, m, Y, r = data
            if key < X:
                return _Tree23(
                    (l._insert(key), X, m, Y, r)
                )._insert_upwards_phase()
            if key == X:
                return _Tree23((l, key, m, Y, r))
            if key < Y:
                return _Tree23(
                    (l, X, m._insert(key), Y, r)
                )._insert_upwards_phase()
            if key == Y:
                return _Tree23((l, X, m, key, r))
            return _Tree23(
                (l, X, m, Y, r._insert(key))
            )._insert_upwards_phase()
        raise ValueError('Invalid 2-3 tree')

    def _insert_upwards_phase(self) -> '_Tree23':
        if self.is_2_node():
            q, X, r = self._data
            if q._is_kicked_up_node():
                # 2-node upstairs, kicked up node on left
                _, l, w, m = q._data
                return _Tree23((l, w, m, X, r))
            if r._is_kicked_up_node():
                # 2-node upstairs, kicked up node on right
                _, m, w, r = r._data
                l = q
                return _Tree23((l, X, m, w, r))
            return self
        if self.is_3_node():
            a, X, c, Y, d = self._data
            if a._is_kicked_up_node():
                _, a, w, b = a._data
                return _Tree23(
                    ('up', _Tree23((a, w, b)), X, _Tree23((c, Y, d)))
                )
            if c._is_kicked_up_node():
                _, b, w, c = c._data
                return _Tree23(
                    ('up', _Tree23((a, X, b)), w, _Tree23((c, Y, d)))
                )
            if d._is_kicked_up_node():
                b = c
                _, c, w, d = d._data
                return _Tree23(
                    ('up', _Tree23((a, X, b)), Y, _Tree23((c, w, d)))
                )
        return self

    def insert(self, key) -> '_Tree23':
        """Insert key into the tree and return a new tree.

        This method should only be called on the root of a tree."""

        tree = self._insert(key)
        if tree._is_kicked_up_node():
            return _Tree23(tree._data[1:])
        return tree

    def _delete(self, key) -> '_Tree23':
        data = self._data
        if self.is_leaf():
            return _leaf_23_tree
        if self.is_2_node():
            p, a, q = data
            if key < a:
                p_ = p._delete(key)
                return _Tree23((p_, a, q))._delete_upwards_phase()
            if key == a:
                if self._is_2_node_terminal():
                    return _Tree23((p, self.__hole, q))._delete_upwards_phase()
                pred = p.max()
                return _Tree23(
                    (p._delete(pred), pred, q)
                )._delete_upwards_phase()
            q_ = q._delete(key)
            return _Tree23((p, a, q_))._delete_upwards_phase()
        if self.is_3_node():
            l, X, m, Y, r = data
            if key < X:
                return _Tree23(
                    (l._delete(key), X, m, Y, r)
                )._delete_upwards_phase()
            if key == X:
                if self._is_3_node_terminal():
                    return _Tree23(
                        (l, self.__hole, m, Y, r)
                    )._delete_upwards_phase()
                pred = l.max()
                return _Tree23(
                    (l._delete(pred), pred, m, Y, r)
                )._delete_upwards_phase()
            if key < Y:
                return _Tree23(
                    (l, X, m._delete(key), Y, r)
                )._delete_upwards_phase()
            if key == Y:
                if self._is_3_node_terminal():
                    return _Tree23(
                        (l, X, m, self.__hole, r)
                    )._delete_upwards_phase()
                pred = m.max()
                return _Tree23(
                    (l, X, m._delete(pred), pred, r)
                )._delete_upwards_phase()
            return _Tree23(
                (l, X, m, Y, r._delete(key))
            )._delete_upwards_phase()
        raise ValueError('Invalid 2-3 tree')

    def _delete_upwards_phase(self) -> '_Tree23':
        if self.is_3_node():
            w, x, alpha, y, d = self._data
            if self._is_3_node_terminal():
                if x is self.__hole:
                    return _Tree23((_leaf_23_tree, y, _leaf_23_tree))
                if y is self.__hole:
                    return _Tree23((_leaf_23_tree, x, _leaf_23_tree))
            if w._is_hole_node():
                a = w._data[1]
                if alpha.is_2_node():
                    z = y
                    b, y, c = alpha._data
                    if all(
                        map(
                            lambda h: h == d.height - 1,
                            (a.height, b.height, c.height),
                        )
                    ):
                        # 3-node parent, 2-node sibling, hole on left, height condition
                        return _Tree23((_Tree23((a, x, b, y, c)), z, d))
                if alpha.is_3_node():
                    w = x
                    z = y
                    e = d
                    b, x, c, y, d = alpha._data
                    if all(
                        map(
                            lambda h: h == e.height - 1,
                            (a.height, b.height, c.height, d.height),
                        )
                    ):
                        # 3-node parent, 3-parent sibling in middle, hole on left, right condition
                        return _Tree23(
                            (_Tree23((a, w, b)), x, _Tree23((c, y, d)), z, e)
                        )
            if alpha._is_hole_node():
                if w.is_2_node():
                    z = y
                    y = x
                    a, x, b = w._data
                    c = alpha._data[1]
                    if all(
                        map(
                            lambda h: h == d.height - 1,
                            (a.height, b.height, c.height),
                        )
                    ):
                        # 3-node parent, 2-node sibling on left, hole in middle, height condition
                        return _Tree23((_Tree23((a, x, b, y, c)), z, d))
                if w.is_3_node():
                    z = y
                    y = x
                    a, w, b, x, c = w._data
                    e = d
                    d = alpha._data[1]
                    if all(
                        map(
                            lambda h: h == e.height - 1,
                            (a.height, b.height, c.height, d.height),
                        )
                    ):
                        # 3-node parent, 3-node sibling on left, hole in middle, height condition
                        return _Tree23(
                            (_Tree23((a, w, b)), x, _Tree23((c, y, d)), z, e)
                        )
                if d.is_2_node():
                    a = w
                    b = alpha._data[1]
                    c, z, d = d._data
                    if all(
                        map(
                            lambda h: h == a.height - 1,
                            (b.height, c.height, d.height),
                        )
                    ):
                        return _Tree23((a, x, _Tree23((b, y, c, z, d))))
                if d.is_3_node():
                    a = w
                    w = x
                    b = alpha._data[1]
                    x = y
                    c, y, d, z, e = d._data
                    if all(
                        map(
                            lambda h: h == a.height - 1,
                            (b.height, c.height, d.height, e.height),
                        )
                    ):
                        # 3-node parent, 3-node sibling on right, hole in middle, height condition
                        return _Tree23(
                            (a, w, _Tree23((b, x, c)), y, _Tree23((d, z, e)))
                        )
            if d._is_hole_node():
                a = w
                if alpha.is_2_node():
                    z = y
                    b, y, c = alpha._data
                    d = d._data[1]
                    if all(
                        map(
                            lambda h: h == a.height - 1,
                            (b.height, c.height, d.height),
                        )
                    ):
                        # 3-node parent, 2-node sibling in middle, hole on right, height condition
                        return _Tree23((a, x, _Tree23((b, y, c, z, d))))
                if alpha.is_3_node():
                    w = x
                    z = y
                    e = d._data[1]
                    b, x, c, y, d = alpha._data
                    if all(
                        map(
                            lambda h: h == a.height - 1,
                            (b.height, c.height, d.height, e.height),
                        )
                    ):
                        # 3-node parent, 3-node sibling in middle, hole on right, height condition
                        return _Tree23(
                            (a, w, _Tree23((b, x, c)), y, _Tree23((d, z, e)))
                        )
            # 3-node that either has no in data or children, or has bad heights
            return self
        if self.is_2_node():
            left, x, right = self._data
            if self._is_2_node_terminal():
                if x is self.__hole:
                    return _Tree23((x, _leaf_23_tree))
            if left._is_hole_node():
                if right.is_2_node():
                    # 2-node parent, 2-node sibling, hole on left
                    l = left._data[1]
                    m, y, r = right._data
                    return _Tree23((self.__hole, _Tree23((l, x, m, y, r))))
                if right.is_3_node():
                    # 2-node parent, 3-node sibling, hole on left
                    a = left._data[1]
                    b, y, c, z, d = right._data
                    return _Tree23((_Tree23((a, x, b)), y, _Tree23((c, z, d))))
            if right._is_hole_node():
                if left.is_2_node():
                    # 2-node parent, 2-node sibling, hole on right
                    r = right._data[1]
                    y = x
                    l, x, m = left._data
                    return _Tree23((self.__hole, _Tree23((l, x, m, y, r))))
                if left.is_3_node():
                    # 2-node parent, 3-node sibling, hole on right
                    z = x
                    d = right._data[1]
                    a, x, b, y, c = left._data
                    return _Tree23((_Tree23((a, x, b)), y, _Tree23((c, z, d))))
            # no hole in key or children
            return self
        raise RuntimeError(f'Missing case in delete for {self!r}')

    def delete(self, key) -> '_Tree23':
        tree = self._delete(key)
        if tree._is_hole_node():
            return tree._data[1]
        return tree

    def max(self) -> Any:
        tree = self
        while not tree.is_leaf():
            if tree.is_2_node():
                if tree._is_2_node_terminal():
                    return tree._data[1]
                tree = tree._data[2]
            if tree.is_3_node():
                if tree._is_3_node_terminal():
                    return tree._data[3]
                tree = tree._data[4]
        raise ValueError('Empty 2-3 tree has no max')

    __hole = _Tree23Hole()

    def is_leaf(self) -> bool:
        return len(self._data) == 0

    def is_2_node(self) -> bool:
        return len(self._data) == 3

    def is_3_node(self) -> bool:
        return len(self._data) == 5

    def _is_kicked_up_node(self) -> bool:
        return len(self._data) == 4 and self._data[0] == 'up'

    def _is_3_node_terminal(self) -> bool:
        return all(
            map(
                lambda t: t.is_leaf(),
                (self._data[0], self._data[2], self._data[4]),
            )
        )

    def _is_2_node_terminal(self) -> bool:
        return all(map(lambda t: t.is_leaf(), (self._data[0], self._data[2])))

    def _is_hole_node(self) -> bool:
        return len(self._data) == 2 and self._data[0] is self.__hole

    def __repr__(self) -> str:
        return f'{type(self).__qualname__}({self._data!r})'


_leaf_23_tree = _Tree23(())
