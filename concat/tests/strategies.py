from concat.lex import Token
from concat.parse import (
    SimpleValueWordNode,
    NotImplWordNode,
    NoneWordNode,
    EllipsisWordNode,
)
from concat.typecheck.types import (
    IndividualType,
    SequenceVariable,
    StackItemType,
)
from hypothesis.strategies import (
    SearchStrategy,
    booleans,
    composite,
    from_type,
    iterables,
    lists,
    register_type_strategy,
    sampled_from,
)
from typing import (
    Iterable,
    Sequence,
    Type,
)


def _iterable_strategy(type: Type[Iterable]) -> SearchStrategy[Iterable]:
    @composite
    def strategy(draw) -> Iterable:
        if hasattr(type, '__args__') and type.__args__ == (StackItemType,):
            list = []
            if draw(booleans()):
                list.append(draw(from_type(SequenceVariable)))
            list += draw(lists(from_type(IndividualType), max_size=10))
            return list
        cls = draw(sampled_from([list, tuple, set, frozenset]))
        return cls(
            draw(iterables(getattr(type, '__args__', object), max_size=10))
        )

    return strategy()


def _sequence_strategy(type: Type[Sequence]) -> SearchStrategy[Sequence]:
    @composite
    def strategy(draw) -> Sequence:
        cls = draw(sampled_from([list, tuple]))
        return cls(draw(_iterable_strategy(type)))

    return strategy()


def _simple_value_word_node_strategy(
    type: Type[SimpleValueWordNode],
) -> SearchStrategy[SimpleValueWordNode]:
    @composite
    def strategy(draw) -> SimpleValueWordNode:
        cls = draw(
            sampled_from([NotImplWordNode, NoneWordNode, EllipsisWordNode])
        )
        return cls(draw(from_type(Token)))

    return strategy()


register_type_strategy(Iterable, _iterable_strategy)
register_type_strategy(Sequence, _sequence_strategy)
register_type_strategy(SimpleValueWordNode, _simple_value_word_node_strategy)
