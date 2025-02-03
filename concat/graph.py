from collections.abc import Mapping, Iterable, Sequence, Iterator


def cycles[T](graph: Mapping[T, Iterable[T]]) -> Iterator[Sequence[T]]:
    indices: dict[T, int] = {}
    lowlinks: dict[T, int] = {}
    stack_contents: set[T] = set()
    index = 0

    def strong_connect(vertex: T) -> Iterator[Sequence[T]]:
        nonlocal index

        indices[vertex] = index
        lowlinks[vertex] = index
        index += 1
        stack.append(vertex)
        stack_contents.add(vertex)

        for successor in graph.get(vertex, []):
            if successor not in indices:
                yield from strong_connect(successor)
                lowlinks[vertex] = min(lowlinks[vertex], lowlinks[successor])
            elif successor in stack_contents:
                lowlinks[vertex] = min(lowlinks[vertex], indices[successor])

        if lowlinks[vertex] == indices[vertex]:
            scc = []
            while stack[-1] != vertex:
                node_in_scc = stack.pop()
                stack_contents.remove(node_in_scc)
                scc.append(node_in_scc)
            stack.pop()  # the current vertex
            stack_contents.remove(vertex)
            scc.append(vertex)
            yield scc

    # Tarjan's algorithm
    stack: list[T] = []
    for vertex in _vertices(graph):
        if vertex not in indices:
            yield from strong_connect(vertex)


def _vertices[T](graph: Mapping[T, Iterable[T]]) -> set[T]:
    vertices = set(graph)
    for successors in graph.values():
        vertices |= set(successors)
    return vertices


def graph_from_edges[T](
    edges: Iterable[tuple[T, T]],
) -> Mapping[T, Iterable[T]]:
    graph: dict[T, set[T]] = {}
    for src, dest in edges:
        preds = graph.get(src, set())
        preds.add(dest)
        graph[src] = preds
    return graph
