import concat.level0.parse as parse
from concat.level0.lex import Token
import concat.level0.transpile
import unittest
import ast


class TestTopLevelVisitor(unittest.TestCase):

    def setUp(self) -> None:
        self.__visitors = concat.level0.transpile.VisitorDict()
        self.__visitors.extend_with(concat.level0.transpile.level_0_extension)

    def test_top_level_visitor(self) -> None:
        encoding = Token()
        encoding.type = 'ENCODING'
        node = parse.TopLevelNode(encoding, [])
        try:
            py_node = self.__visitors.visit(node)
        except concat.level0.transpile.VisitFailureException:
            message = '{} was not accepted by the top level visitor'.format(node)
            self.fail(msg=message)
        self.assertIsInstance(py_node, ast.Module, msg='Python node is not a module')
