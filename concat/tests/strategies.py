from concat.typecheck.types import (
    IndividualKind,
    IndividualType,
    ItemVariable,
    ObjectType,
    PythonFunctionType,
    SequenceVariable,
    StackEffect,
    TypeApplication,
    TypeSequence,
    _OptionalType,
    _PythonOverloadedType,
    no_return_type,
    optional_type,
    py_function_type,
    py_overloaded_type,
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
    tuples,
)
from typing import Type


def _type_sequence_strategy(
    individual_type_strategy: SearchStrategy[IndividualType],
    no_rest_var: bool = False,
) -> SearchStrategy[TypeSequence]:
    return builds(
        lambda maybe_seq_var, rest: TypeSequence(maybe_seq_var + rest),
        lists(from_type(SequenceVariable), max_size=0 if no_rest_var else 1),
        lists(individual_type_strategy, max_size=5),
    )


def _object_type_strategy(
    individual_type_strategy: SearchStrategy[IndividualType],
) -> SearchStrategy[ObjectType]:
    return recursive(
        builds(
            ObjectType,
            attributes=dictionaries(text(), individual_type_strategy),
        ),
        lambda children: builds(
            ObjectType,
            attributes=dictionaries(text(), individual_type_strategy),
        ),
        max_leaves=10,
    )


def _py_function_strategy(
    individual_type_strategy: SearchStrategy[IndividualType],
) -> SearchStrategy[PythonFunctionType]:
    return builds(
        lambda args: py_function_type[args],
        tuples(
            _type_sequence_strategy(
                individual_type_strategy, no_rest_var=True
            ),
            individual_type_strategy,
        ),
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
        builds(ItemVariable, just(IndividualKind)), ItemVariable
    )
    | _mark_individual_type_strategy(
        just(no_return_type), type(no_return_type)
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
    )
    | _mark_individual_type_strategy(
        _py_function_strategy(children),
        PythonFunctionType,
    )
    | _mark_individual_type_strategy(
        builds(
            lambda arg: py_overloaded_type[arg],
            _type_sequence_strategy(
                _py_function_strategy(children), no_rest_var=True
            ),
        ),
        _PythonOverloadedType,
    )
    | _mark_individual_type_strategy(
        builds(
            lambda args: optional_type[args],
            tuples(children),
        ),
        _OptionalType,
    ),
    max_leaves=50,
)

for subclass in _individual_type_subclasses:
    if subclass not in [TypeApplication]:
        assert subclass in _individual_type_strategies, subclass

register_type_strategy(IndividualType, _individual_type_strategy)
register_type_strategy(
    ObjectType, _object_type_strategy(_individual_type_strategy)
)
register_type_strategy(
    TypeSequence, _type_sequence_strategy(_individual_type_strategy)
)
