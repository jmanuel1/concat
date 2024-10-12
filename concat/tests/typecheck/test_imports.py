from concat.parse import ImportStatementNode
from concat.typecheck import Environment, infer
from concat.typecheck.types import (
    BoundVariable,
    GenericType,
    SequenceKind,
    StackEffect,
    TypeSequence,
    get_module_type,
)
import pathlib
from unittest import TestCase


class TestImports(TestCase):
    def test_import_generates_module_type(self) -> None:
        """Test that imports generate a module type for the right namespace."""
        test_module_path = (
            pathlib.Path(__file__) / '../../fixtures/'
        ).resolve()
        env = infer(
            Environment(),
            [ImportStatementNode('imported_module')],
            is_top_level=True,
            source_dir=test_module_path,
        )[2]
        ty = env['imported_module']
        seq_var = BoundVariable(kind=SequenceKind)
        ty.constrain_and_bind_variables(
            GenericType(
                [seq_var],
                StackEffect(
                    TypeSequence([seq_var]),
                    TypeSequence([seq_var, get_module_type()]),
                ),
            ),
            set(),
            [],
        )
