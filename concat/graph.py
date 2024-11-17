import graphlib
from collections.abc import Mapping, Iterable, Sequence, Iterator


def cycles[T](graph: Mapping[T, Iterable[T]]) -> Iterator[Sequence[T]]:
    graph = {**graph}
    while True:
        ts = graphlib.TopologicalSorter(graph)
        try:
            order = ts.static_order()
            yield from map(lambda node: [node], order)
            break
        except graphlib.CycleError as e:
            cycle = e.args[1]
            yield cycle[:-1]
            for node in cycle[:-1]:
                del graph[node]
            for node, preds in graph.items():
                graph[node] = [n for n in graph[node] if n not in cycle]


def _adjacent_pairs[T](it: Iterable[T]) -> Iterator[tuple[T, T]]:
    itor = iter(it)
    last = next(itor)
    for x in itor:
        yield (last, x)
        last = x
