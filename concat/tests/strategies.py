from concat.typecheck import TypeChecker
from concat.typecheck.context import current_context
from concat.typecheck.types import (
    IndividualKind,
    IndividualType,
    ItemVariable,
    ObjectType,
    PythonFunctionType,
    PythonOverloadedType,
    SequenceVariable,
    StackEffect,
)
from concat.typecheck.types import Type as ConcatType
from concat.typecheck.types import (
    TypeSequence,
    VariableArgumentPack,
    _OptionalType,
)
from hypothesis.strategies import (
    DrawFn,
    SearchStrategy,
    builds,
    composite,
    dictionaries,
    from_type,
    just,
    lists,
    recursive,
    register_type_strategy,
    text,
    tuples,
)


def _type_sequence_strategy(
    context: TypeChecker,
    individual_type_strategy: SearchStrategy[ConcatType],
    no_rest_var: bool = False,
) -> SearchStrategy[TypeSequence]:
    return builds(
        lambda maybe_seq_var, rest: TypeSequence(
            context, maybe_seq_var + rest
        ),
        lists(from_type(SequenceVariable), max_size=0 if no_rest_var else 1),
        lists(individual_type_strategy, max_size=5),
    )


def _variable_argument_pack_strategy(
    type_strategy: SearchStrategy[ConcatType],
) -> SearchStrategy[VariableArgumentPack]:
    return builds(
        lambda rest: VariableArgumentPack(rest),
        lists(type_strategy, max_size=5),
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
        max_leaves=5,
    )


def _py_function_strategy(
    context: TypeChecker,
    individual_type_strategy: SearchStrategy[IndividualType],
) -> SearchStrategy[PythonFunctionType]:
    return builds(
        lambda args: PythonFunctionType(context, *args),
        tuples(
            _type_sequence_strategy(
                context, individual_type_strategy, no_rest_var=True
            ),
            individual_type_strategy,
        ),
    )


def _stack_effect_strategy(
    context: TypeChecker, children: SearchStrategy[ConcatType]
) -> SearchStrategy[ConcatType]:
    return builds(
        StackEffect,
        _type_sequence_strategy(context, children),
        _type_sequence_strategy(context, children),
    )


def stack_effect_strategy(context: TypeChecker) -> SearchStrategy[ConcatType]:
    return _stack_effect_strategy(context, _individual_type_strategy(context))


def _individual_type_strategy(
    context: TypeChecker,
) -> SearchStrategy[ConcatType]:
    return recursive(
        builds(ItemVariable, just(IndividualKind))
        | just(context.no_return_type),
        lambda children: _stack_effect_strategy(context, children)
        | _object_type_strategy(children)
        | _py_function_strategy(context, children)
        | builds(
            PythonOverloadedType,
            _variable_argument_pack_strategy(
                _py_function_strategy(context, children),
            ),
        )
        | builds(
            _OptionalType,
            children,
        ),
        max_leaves=5,
    )


individual_type_strategy = _individual_type_strategy


@composite
def _individual_type_strategy_dependent_on_context(draw: DrawFn) -> ConcatType:
    context = current_context.get()
    return draw(_individual_type_strategy(context))


@composite
def _type_sequence_strategy_dependent_on_context(draw: DrawFn) -> ConcatType:
    context = current_context.get()
    return draw(
        _type_sequence_strategy(context, _individual_type_strategy(context))
    )


register_type_strategy(
    IndividualType, _individual_type_strategy_dependent_on_context()
)
register_type_strategy(
    ObjectType,
    _object_type_strategy(_individual_type_strategy_dependent_on_context()),
)
register_type_strategy(
    TypeSequence, _type_sequence_strategy_dependent_on_context()
)


def type_strategy(context: TypeChecker) -> SearchStrategy[ConcatType]:
    return recursive(
        individual_type_strategy(context)
        | _type_sequence_strategy(context, individual_type_strategy(context)),
        _variable_argument_pack_strategy,
    )
