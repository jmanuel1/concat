import concat.visitors
from concat.level0.lex import Token
import concat.level0.parse
import concat.level0.transpile
import concat.level1.parse
import concat.level1.transpile
import unittest
import ast
from typing import cast
import astunparse  # type: ignore


class TestSubVisitors(unittest.TestCase):

    def setUp(self) -> None:
        self.__visitors = concat.visitors.VisitorDict[
            concat.level0.parse.Node, ast.AST]()
        self.__visitors.extend_with(concat.level0.transpile.level_0_extension)
        self.__visitors.extend_with(concat.level1.transpile.level_1_extension)

    def test_none_word_visitor(self) -> None:
        none = Token()
        none.start = (0, 0)
        node = concat.level1.parse.NoneWordNode(none)
        try:
            py_node = self.__visitors['none-word'].visit(node)
        except concat.visitors.VisitFailureException:
            message = '{} was not accepted by the none-word visitor'.format(
                node)
            self.fail(msg=message)
        self.assertIsInstance(
            py_node, ast.Call, msg='Python node is not a call')
        value = cast(ast.NameConstant, cast(ast.Call, py_node).args[0]).value
        self.assertIs(value, None,
                      msg='Python None node does not contain `None`')

    def test_not_impl_word_visitor(self) -> None:
        not_impl = Token()
        not_impl.start = (0, 0)
        node = concat.level1.parse.NotImplWordNode(not_impl)
        try:
            py_node = self.__visitors['not-impl-word'].visit(node)
        except concat.visitors.VisitFailureException:
            message_template = '{} was not accepted by the not-impl-word '
            'visitor'
            message = message_template.format(node)
            self.fail(msg=message)
        self.assertIsInstance(
            py_node, ast.Call, msg='Python node is not a call')
        identifier = cast(ast.Name, cast(ast.Call, py_node).args[0]).id
        message = 'Python Name node does not contain "NotImplemented"'
        self.assertEqual(identifier, 'NotImplemented', msg=message)

    def test_ellipsis_word_visitor(self) -> None:
        ellipsis = Token()
        ellipsis.start = (0, 0)
        node = concat.level1.parse.EllipsisWordNode(ellipsis)
        try:
            py_node = self.__visitors['ellipsis-word'].visit(node)
        except concat.visitors.VisitFailureException:
            message_template = '{} was not accepted by the ellipsis-word '
            'visitor'
            message = message_template.format(node)
            self.fail(msg=message)
        self.assertIsInstance(
            py_node, ast.Call, msg='Python node is not a call')
        message = 'The Python node within the call is not an Ellipsis'
        self.assertIsInstance(
            cast(ast.Call, py_node).args[0], ast.Ellipsis, msg=message)

    def test_subscription_word_visitor(self) -> None:
        node = concat.level1.parse.SubscriptionWordNode([])
        for visitor in {'subscription-word', 'word'}:
            try:
                py_node = self.__visitors[visitor].visit(node)
            except concat.visitors.VisitFailureException:
                message_template = '{} was not accepted by {} visitor'
                message = message_template.format(node, visitor)
                self.fail(msg=message)
            self.assertIsInstance(
                py_node, ast.expr, msg='Python node is not a expression')

    def test_slice_word_visitor(self) -> None:
        node = concat.level1.parse.SliceWordNode(([], [], []))
        for visitor in {'slice-word', 'word'}:
            try:
                py_node = self.__visitors[visitor].visit(node)
            except concat.visitors.VisitFailureException:
                message_template = '{} was not accepted by the {} visitor'
                message = message_template.format(node, visitor)
                self.fail(msg=message)
            self.assertIsInstance(
                py_node, ast.expr, msg='Python node is not a expression')

    def test_slice_word_visitor_with_step(self) -> None:
        two_token = concat.level0.lex.Token()
        two_token.type, two_token.value = 'NUMBER', '2'
        two = concat.level0.parse.NumberWordNode(two_token)
        node = concat.level1.parse.SliceWordNode(([], [], [two]))
        try:
            py_node = self.__visitors['slice-word'].visit(node)
        except concat.visitors.VisitFailureException:
            message_template = '{} was not accepted by the slice-word '
            'visitor'
            message = message_template.format(node)
            self.fail(msg=message)
        self.assertIn('2', astunparse.unparse(py_node),
                      msg='Python node does not contain 2')

    def test_bytes_word_visitor(self) -> None:
        bytes_token = concat.level0.lex.Token()
        bytes_token.start, bytes_token.value = (0, 0), 'b"bytes"'
        node = concat.level1.parse.BytesWordNode(bytes_token)

        def test(visitor: str) -> None:
            try:
                py_node = self.__visitors[visitor].visit(node)
            except concat.visitors.VisitFailureException:
                message_template = '{} was not accepted by the {} '
                'visitor'
                message = message_template.format(node, visitor)
                self.fail(msg=message)
            self.assertIsInstance(
                py_node, ast.Call, msg='Python node is not a call')

        test('bytes-word')
        test('literal-word')
