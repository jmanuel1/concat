from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING

from concat.typecheck.types import (
    BoundVariable,
    GenericType,
    ItemKind,
    ObjectType,
    Type,
    TypeSequence,
)

if TYPE_CHECKING:
    from concat.typecheck import TypeChecker


_a_var = BoundVariable(ItemKind)


def types0(context: TypeChecker) -> Mapping[str, Type]:
    return {
        'Intersection': context.intersection_type,
        'iterable': context.iterable_type,
        'iterator': context.iterator_type,
        'Optional': context.optional_type,
        'py_function': context.py_function_type,
    }


def types(context: TypeChecker) -> Mapping[str, Type]:
    return {
        'addable': context.addable_type,
        'raddable': context.raddable_type,
        'leq_comparable': context.leq_comparable_type,
        'lt_comparable': context.lt_comparable_type,
        'geq_comparable': context.geq_comparable_type,
        'gt_comparable': context.gt_comparable_type,
        # TODO: Separate type-check-time environment from runtime environment.
        'NoReturn': context.no_return_type,
        'subscriptable': context.subscriptable_type,
        'subtractable': context.subtractable_type,
        'rsubtractable': context.rsubtractable_type,
        'context_manager': context.context_manager_type,
        'py_overloaded': context.py_overloaded_type,
        'SupportsAbs': GenericType(
            [_a_var],
            ObjectType(
                {
                    '__abs__': context.py_function_type.apply(
                        context,
                        [context.tuple_forward_var.apply(context, []), _a_var],
                    ),
                },
            ),
        ),
    }
