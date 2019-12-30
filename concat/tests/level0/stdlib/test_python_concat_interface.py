"""Python-Concat interface tests.

Tests that the boundary between Python and Concat is correct."""
import concat.libconcat as libconcat
import unittest
import unittest.mock as mock
import concat.stdlib.builtins as builtins
from concat.level0.stdlib.types import Quotation
import concat.level0.stdlib.pyinterop
import concat.level0.lex
import concat.level0.transpile
import concat.level0.execute
import concat.level0.parse
import ast
from typing import List, cast


class TestIntoPythonFromConcat(unittest.TestCase):
    """Test the Python-Concat interface going into Python from Concat."""

    def test_python_function(self):
        """Python function call test (from Concat).

        Test that a normal Python is treated as if it had the stack effect
        kwargs args -- func(*args, **kwargs) when called with py_call."""
        stack, stash = [Quotation([]), Quotation([0]), bool], []
        concat.level0.stdlib.pyinterop.py_call(stack, stash)
        self.assertEqual(stack, [False], msg='py_call has incorrect stack effect')
class TestIntoConcatFromPython(unittest.TestCase):
    """Test the Python-Concat interface going into Concat from Python."""

    def test_modules_are_callable(self):
        """Test that imported modules become callable.

        Test that a module imported through import <name> pushes itself onto
        the stack when referred to by name (i.e. module is $module)."""
        namespace = {}
        lexer = concat.level0.lex.Lexer()
        lexer.input('import sys\nsys')
        tokens = []
        while True:
            token = lexer.token()
            if token is None:
                break
            tokens.append(token)
        parser = concat.level0.parse.ParserDict()
        parser.extend_with(concat.level0.parse.level_0_extension)
        concat_ast = parser.parse(tokens)
        transpiler = concat.level0.transpile.VisitorDict[concat.level0.parse.Node, ast.AST]()
        transpiler.extend_with(concat.level0.transpile.level_0_extension)
        prog = cast(ast.Module, transpiler.visit(concat_ast))
        concat.level0.execute.execute('<test>', prog, namespace)
        self.assertIs(namespace['stack'][-1], namespace['sys'], msg='module is not self-pushing')
