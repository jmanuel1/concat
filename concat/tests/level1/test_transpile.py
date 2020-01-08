from concat.level0.lex import Token
import concat.level0.transpile
import concat.level1.parse
import concat.level1.transpile
import unittest
import ast
from typing import cast


class TestSubVisitors(unittest.TestCase):

    def setUp(self) -> None:
        self.__visitors = concat.level0.transpile.VisitorDict[
            concat.level0.parse.Node, ast.AST]()
        self.__visitors.extend_with(concat.level0.transpile.level_0_extension)
        self.__visitors.extend_with(concat.level1.transpile.level_1_extension)

    def test_none_word_visitor(self) -> None:
        none = Token()
        none.start = (0, 0)
        node = concat.level1.parse.NoneWordNode(none)
        try:
            py_node = self.__visitors['none-word'].visit(node)
        except concat.level0.transpile.VisitFailureException:
            message = '{} was not accepted by the none-word visitor'.format(
                node)
            self.fail(msg=message)
        self.assertIsInstance(
            py_node, ast.Call, msg='Python node is not a call')
        value = cast(ast.NameConstant, cast(ast.Call, py_node).args[0]).value
        self.assertIs(value, None,
                      msg='Python None node does not contain `None`')
