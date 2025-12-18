import pathlib
from unittest import TestCase

from concat.parse import ImportStatementNode
from concat.typecheck import Environment, TypeChecker
from concat.typecheck.context import change_context
from concat.typecheck.types import (
    BoundVariable,
    GenericType,
    SequenceKind,
    StackEffect,
    TypeSequence,
)

context = TypeChecker()
infer = context.infer


class TestImports(TestCase):
    def test_import_generates_module_type(self) -> None:
        """Test that imports generate a module type for the right namespace."""
        test_module_path = (
            pathlib.Path(__file__) / '../../fixtures/'
        ).resolve()
        env = infer(
            Environment(),
            [ImportStatementNode('imported_module', (0, 0), (0, 0))],
            is_top_level=True,
            source_dir=test_module_path,
        )[1]
        ty = env['imported_module']
        with change_context(context):
            seq_var = BoundVariable(kind=SequenceKind)
            ty.constrain_and_bind_variables(
                context,
                GenericType(
                    [seq_var],
                    StackEffect(
                        TypeSequence(context, [seq_var]),
                        TypeSequence(context, [seq_var, context.module_type]),
                    ),
                ),
                set(),
                [],
            )
