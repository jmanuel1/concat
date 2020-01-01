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


class TestSubVisitors(unittest.TestCase):

    def setUp(self) -> None:
        self.__visitors = concat.level0.transpile.VisitorDict[
            concat.level0.parse.Node, ast.AST]()
        self.__visitors.extend_with(concat.level0.transpile.level_0_extension)

    def test_statement_visitor(self) -> None:
        module = Token()
        module.value = 'ast'
        # use a concrete class
        node = parse.ImportStatementNode(module, (0, 0))
        try:
            py_node = self.__visitors['statement'].visit(node)
        except concat.level0.transpile.VisitFailureException:
            message = '{} was not accepted by the statement visitor'.format(node)
            self.fail(msg=message)
        self.assertIsInstance(py_node, ast.stmt, msg='Python node is not a statement')

    def test_word_visitor(self) -> None:
        number = Token()
        number.start = (0, 0)
        number.value = '6'
        # use a concrete class
        node = parse.NumberWordNode(number)
        try:
            py_node = self.__visitors['word'].visit(node)
        except concat.level0.transpile.VisitFailureException:
            message = '{} was not accepted by the word visitor'.format(node)
            self.fail(msg=message)
        self.assertIsInstance(py_node, ast.expr, msg='Python node is not a expression')

    def test_string_word_visitor(self) -> None:
        string = Token()
        string.start = (0, 0)
        string.value = '"string"'
        node = parse.StringWordNode(string)
        try:
            py_node = self.__visitors['string-word'].visit(node)
        except concat.level0.transpile.VisitFailureException:
            message = '{} was not accepted by the string-word visitor'.format(node)
            self.fail(msg=message)
        self.assertIsInstance(py_node, ast.Str, msg='Python node is not a string')

    def test_attribute_word_visitor(self) -> None:
        name = Token()
        name.start = (0, 0)
        name.value = 'attr'
        node = parse.AttributeWordNode(name)
        try:
            py_node = self.__visitors['attribute-word'].visit(node)
        except concat.level0.transpile.VisitFailureException:
            message = '{} was not accepted by the attribute-word visitor'.format(node)
            self.fail(msg=message)
        self.assertIsInstance(py_node, ast.Attribute, msg='Python node is not a attribute')
