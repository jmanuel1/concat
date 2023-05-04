from concat.lex import Token
from concat.typecheck.types import (
    IndividualType,
    IndividualVariable,
    ObjectType,
    SequenceVariable,
    StackEffect,
    TypeSequence,
)
from hypothesis.strategies import (
    SearchStrategy,
    builds,
    dictionaries,
    from_type,
    just,
    lists,
    none,
    recursive,
    register_type_strategy,
    text,
)
from typing import (
    Iterable,
    Sequence,
    Type,
)


def _type_sequence_strategy(
    individual_type_strategy: SearchStrategy[IndividualType],
) -> SearchStrategy[TypeSequence]:
    return builds(
        lambda maybe_seq_var, rest: TypeSequence(maybe_seq_var + rest),
        lists(from_type(SequenceVariable), max_size=1),
        lists(individual_type_strategy, max_size=10),
    )


def _object_type_strategy(
    individual_type_strategy: SearchStrategy[IndividualType],
) -> SearchStrategy[ObjectType]:
    return recursive(
        builds(
            ObjectType,
            attributes=dictionaries(text(), individual_type_strategy),
            nominal_supertypes=lists(individual_type_strategy),
            _type_arguments=lists(
                from_type(SequenceVariable)
                | individual_type_strategy
                | _type_sequence_strategy(individual_type_strategy)
            ),
            _head=none(),
            _other_kwargs=just({}),
        ),
        lambda children: builds(
            ObjectType,
            attributes=dictionaries(text(), individual_type_strategy),
            nominal_supertypes=lists(individual_type_strategy),
            _type_arguments=lists(
                from_type(SequenceVariable)
                | individual_type_strategy
                | _type_sequence_strategy(individual_type_strategy)
            ),
            _head=children,
            _other_kwargs=just({}),
        ),
        max_leaves=50,
    )


_individual_type_subclasses = IndividualType.__subclasses__()
_individual_type_strategies = {}


def _mark_individual_type_strategy(
    strategy: SearchStrategy[IndividualType], type_: Type[IndividualType]
) -> SearchStrategy[IndividualType]:
    _individual_type_strategies[type_] = strategy
    return strategy


_individual_type_strategy = recursive(
    _mark_individual_type_strategy(
        from_type(IndividualVariable), IndividualVariable
    ),
    lambda children: _mark_individual_type_strategy(
        builds(
            StackEffect,
            _type_sequence_strategy(children),
            _type_sequence_strategy(children),
        ),
        StackEffect,
    )
    | _mark_individual_type_strategy(
        _object_type_strategy(children), ObjectType
    ),
    max_leaves=50,
)

for subclass in _individual_type_subclasses:
    assert subclass in _individual_type_strategies, subclass

register_type_strategy(IndividualType, _individual_type_strategy)
register_type_strategy(
    ObjectType, _object_type_strategy(_individual_type_strategy)
)
register_type_strategy(
    TypeSequence, _type_sequence_strategy(_individual_type_strategy)
)
