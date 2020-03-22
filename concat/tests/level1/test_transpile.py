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

    def test_tuple_word_visitor(self) -> None:
        node = concat.level1.parse.TupleWordNode((), (0, 0))

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

        test('tuple-word')
        test('literal-word')

    def test_list_word_visitor(self) -> None:
        node = concat.level1.parse.ListWordNode((), (0, 0))

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

        test('list-word')
        test('literal-word')

    def test_del_statement_visitor(self) -> None:
        name_token = concat.level0.lex.Token()
        name_token.value, name_token.start = 'a', (0, 0)
        name = concat.level0.parse.NameWordNode(name_token)
        node = concat.level1.parse.DelStatementNode([name])

        def test(visitor: str) -> None:
            try:
                py_node = self.__visitors[visitor].visit(node)
            except concat.visitors.VisitFailureException:
                message_template = '{} was not accepted by the {} '
                'visitor'
                message = message_template.format(node, visitor)
                self.fail(msg=message)
            self.assertIsInstance(
                py_node, ast.Delete, msg='Python node is not a del statement')

        test('del-statement')
        test('statement')

    def test_set_word_visitor(self) -> None:
        node = concat.level1.parse.SetWordNode((), (0, 0))

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

        test('set-word')
        test('literal-word')

    def test_dict_word_visitor(self) -> None:
        node = concat.level1.parse.DictWordNode((), (0, 0))

        def test(visitor: str) -> None:
            try:
                py_node = self.__visitors[visitor].visit(node)
            except concat.visitors.VisitFailureException:
                message_template = '{} was not accepted by the {} visitor'
                message = message_template.format(node, visitor)
                self.fail(msg=message)
            self.assertIsInstance(
                py_node, ast.Call, msg='Python node is not a call')

        test('dict-word')
        test('literal-word')

    def test_yield_word_visitor(self) -> None:
        token = concat.level0.lex.Token()
        token.start = (0, 0)
        node = concat.level1.parse.YieldWordNode(token)

        def test(visitor: str) -> None:
            try:
                py_node = self.__visitors[visitor].visit(node)
            except concat.visitors.VisitFailureException:
                message_template = '{} was not accepted by the {} visitor'
                message = message_template.format(node, visitor)
                self.fail(msg=message)
            self.assertIsInstance(
                py_node, ast.expr, msg='Python node is not an expression')

        test('yield-word')
        test('word')

    def test_async_funcdef_statement_visitor(self) -> None:
        name_token = concat.level0.lex.Token()
        name_token.value, name_token.start = 'a', (0, 0)
        node = concat.level1.parse.AsyncFuncdefStatementNode(
            name_token, [], [], [], (0, 0))

        def test(visitor: str) -> None:
            try:
                py_node = self.__visitors[visitor].visit(node)
            except concat.visitors.VisitFailureException:
                message_template = '{} was not accepted by the {} visitor'
                message = message_template.format(node, visitor)
                self.fail(msg=message)
            self.assertIsInstance(
                py_node, ast.AsyncFunctionDef,
                msg='Python node is not an async function definition')

        test('async-funcdef-statement')
        test('statement')

    def test_funcdef_statement_visitor(self) -> None:
        name_token = concat.level0.lex.Token()
        name_token.value, name_token.start = 'a', (0, 0)
        node = concat.level1.parse.FuncdefStatementNode(
            name_token, [], [], [], (0, 0))

        def test(visitor: str) -> None:
            try:
                py_node = self.__visitors[visitor].visit(node)
            except concat.visitors.VisitFailureException:
                message_template = '{} was not accepted by the {} visitor'
                message = message_template.format(node, visitor)
                self.fail(msg=message)
            self.assertIsInstance(
                py_node, ast.FunctionDef,
                msg='Python node is not a function definition')

        test('funcdef-statement')
        test('statement')

    def test_await_word_visitor(self) -> None:
        token = concat.level0.lex.Token()
        token.start = (0, 0)
        node = concat.level1.parse.AwaitWordNode(token)

        def test(visitor: str) -> None:
            try:
                py_node = self.__visitors[visitor].visit(node)
            except concat.visitors.VisitFailureException:
                message_template = '{} was not accepted by the {} visitor'
                message = message_template.format(node, visitor)
                self.fail(msg=message)
            self.assertIsInstance(
                py_node, ast.expr, msg='Python node is not an expression')

        test('await-word')
        test('word')

    def test_power_word_visitor(self) -> None:
        token = concat.level0.lex.Token()
        token.start = (0, 0)
        node = concat.level1.parse.PowerWordNode(token)

        def test(visitor: str) -> None:
            try:
                py_node = self.__visitors[visitor].visit(node)
            except concat.visitors.VisitFailureException:
                message_template = '{} was not accepted by the {} visitor'
                message = message_template.format(node, visitor)
                self.fail(msg=message)
            self.assertIsInstance(
                py_node, ast.expr, msg='Python node is not an expression')

        test('power-word')
        test('operator-word')
        test('word')

    def test_invert_word_visitor(self) -> None:
        token = concat.level0.lex.Token()
        token.start = (0, 0)
        node = concat.level1.parse.InvertWordNode(token)

        def test(visitor: str) -> None:
            try:
                py_node = self.__visitors[visitor].visit(node)
            except concat.visitors.VisitFailureException:
                message_template = '{} was not accepted by the {} visitor'
                message = message_template.format(node, visitor)
                self.fail(msg=message)
            self.assertIsInstance(
                py_node, ast.expr, msg='Python node is not an expression')

        test('invert-word')
        test('operator-word')
        test('word')

    def test_mul_word_visitor(self) -> None:
        token = concat.level0.lex.Token()
        token.start = (0, 0)
        node = concat.level1.parse.MulWordNode(token)

        def test(visitor: str) -> None:
            try:
                py_node = self.__visitors[visitor].visit(node)
            except concat.visitors.VisitFailureException:
                message_template = '{} was not accepted by the {} visitor'
                message = message_template.format(node, visitor)
                self.fail(msg=message)
            self.assertIsInstance(
                py_node, ast.expr, msg='Python node is not an expression')

        test('mul-word')
        test('operator-word')
        test('word')

    def test_floor_div_word_visitor(self) -> None:
        token = concat.level0.lex.Token()
        token.start = (0, 0)
        node = concat.level1.parse.FloorDivWordNode(token)

        def test(visitor: str) -> None:
            try:
                py_node = self.__visitors[visitor].visit(node)
            except concat.visitors.VisitFailureException:
                message_template = '{} was not accepted by the {} visitor'
                message = message_template.format(node, visitor)
                self.fail(msg=message)
            self.assertIsInstance(
                py_node, ast.expr, msg='Python node is not an expression')

        test('floor-div-word')
        test('operator-word')
        test('word')

    def test_div_word_visitor(self) -> None:
        token = concat.level0.lex.Token()
        token.start = (0, 0)
        node = concat.level1.parse.DivWordNode(token)

        def test(visitor: str) -> None:
            try:
                py_node = self.__visitors[visitor].visit(node)
            except concat.visitors.VisitFailureException:
                message_template = '{} was not accepted by the {} visitor'
                message = message_template.format(node, visitor)
                self.fail(msg=message)
            self.assertIsInstance(
                py_node, ast.expr, msg='Python node is not an expression')

        test('div-word')
        test('operator-word')
        test('word')

    def test_mod_word_visitor(self) -> None:
        token = concat.level0.lex.Token()
        token.start = (0, 0)
        node = concat.level1.parse.ModWordNode(token)

        def test(visitor: str) -> None:
            try:
                py_node = self.__visitors[visitor].visit(node)
            except concat.visitors.VisitFailureException:
                message_template = '{} was not accepted by the {} visitor'
                message = message_template.format(node, visitor)
                self.fail(msg=message)
            self.assertIsInstance(
                py_node, ast.expr, msg='Python node is not an expression')

        test('mod-word')
        test('operator-word')
        test('word')

    def test_add_word_visitor(self) -> None:
        token = concat.level0.lex.Token()
        token.start = (0, 0)
        node = concat.level1.parse.AddWordNode(token)

        def test(visitor: str) -> None:
            try:
                py_node = self.__visitors[visitor].visit(node)
            except concat.visitors.VisitFailureException:
                message_template = '{} was not accepted by the {} visitor'
                message = message_template.format(node, visitor)
                self.fail(msg=message)
            self.assertIsInstance(
                py_node, ast.expr, msg='Python node is not an expression')

        test('add-word')
        test('operator-word')
        test('word')

    def test_subtract_word_visitor(self) -> None:
        token = concat.level0.lex.Token()
        token.start = (0, 0)
        node = concat.level1.parse.SubtractWordNode(token)

        def test(visitor: str) -> None:
            try:
                py_node = self.__visitors[visitor].visit(node)
            except concat.visitors.VisitFailureException:
                message_template = '{} was not accepted by the {} visitor'
                message = message_template.format(node, visitor)
                self.fail(msg=message)
            self.assertIsInstance(
                py_node, ast.expr, msg='Python node is not an expression')

        test('subtract-word')
        test('operator-word')
        test('word')

    def test_left_shift_word_visitor(self) -> None:
        token = concat.level0.lex.Token()
        token.start = (0, 0)
        node = concat.level1.parse.LeftShiftWordNode(token)

        def test(visitor: str) -> None:
            try:
                py_node = self.__visitors[visitor].visit(node)
            except concat.visitors.VisitFailureException:
                message_template = '{} was not accepted by the {} visitor'
                message = message_template.format(node, visitor)
                self.fail(msg=message)
            self.assertIsInstance(
                py_node, ast.expr, msg='Python node is not an expression')

        test('left-shift-word')
        test('operator-word')
        test('word')

    def test_right_shift_word_visitor(self) -> None:
        token = concat.level0.lex.Token()
        token.start = (0, 0)
        node = concat.level1.parse.RightShiftWordNode(token)

        def test(visitor: str) -> None:
            try:
                py_node = self.__visitors[visitor].visit(node)
            except concat.visitors.VisitFailureException:
                message_template = '{} was not accepted by the {} visitor'
                message = message_template.format(node, visitor)
                self.fail(msg=message)
            self.assertIsInstance(
                py_node, ast.expr, msg='Python node is not an expression')

        test('right-shift-word')
        test('operator-word')
        test('word')

    def test_bitwise_and_word_visitor(self) -> None:
        token = concat.level0.lex.Token()
        token.start = (0, 0)
        node = concat.level1.parse.BitwiseAndWordNode(token)

        def test(visitor: str) -> None:
            try:
                py_node = self.__visitors[visitor].visit(node)
            except concat.visitors.VisitFailureException:
                message_template = '{} was not accepted by the {} visitor'
                message = message_template.format(node, visitor)
                self.fail(msg=message)
            self.assertIsInstance(
                py_node, ast.expr, msg='Python node is not an expression')

        test('bitwise-and-word')
        test('operator-word')
        test('word')

    def test_bitwise_xor_word_visitor(self) -> None:
        token = concat.level0.lex.Token()
        token.start = (0, 0)
        node = concat.level1.parse.BitwiseXorWordNode(token)

        def test(visitor: str) -> None:
            try:
                py_node = self.__visitors[visitor].visit(node)
            except concat.visitors.VisitFailureException:
                message_template = '{} was not accepted by the {} visitor'
                message = message_template.format(node, visitor)
                self.fail(msg=message)
            self.assertIsInstance(
                py_node, ast.expr, msg='Python node is not an expression')

        test('bitwise-xor-word')
        test('operator-word')
        test('word')

    def test_bitwise_or_word_visitor(self) -> None:
        token = concat.level0.lex.Token()
        token.start = (0, 0)
        node = concat.level1.parse.BitwiseOrWordNode(token)

        def test(visitor: str) -> None:
            try:
                py_node = self.__visitors[visitor].visit(node)
            except concat.visitors.VisitFailureException:
                message_template = '{} was not accepted by the {} visitor'
                message = message_template.format(node, visitor)
                self.fail(msg=message)
            self.assertIsInstance(
                py_node, ast.expr, msg='Python node is not an expression')

        test('bitwise-or-word')
        test('operator-word')
        test('word')

    def test_less_than_word_visitor(self) -> None:
        token = concat.level0.lex.Token()
        token.start = (0, 0)
        node = concat.level1.parse.LessThanWordNode(token)

        def test(visitor: str) -> None:
            try:
                py_node = self.__visitors[visitor].visit(node)
            except concat.visitors.VisitFailureException:
                message_template = '{} was not accepted by the {} visitor'
                message = message_template.format(node, visitor)
                self.fail(msg=message)
            self.assertIsInstance(
                py_node, ast.expr, msg='Python node is not an expression')

        test('less-than-word')
        test('operator-word')
        test('word')

    def test_greater_than_word_visitor(self) -> None:
        token = concat.level0.lex.Token()
        token.start = (0, 0)
        node = concat.level1.parse.GreaterThanWordNode(token)

        def test(visitor: str) -> None:
            try:
                py_node = self.__visitors[visitor].visit(node)
            except concat.visitors.VisitFailureException:
                message_template = '{} was not accepted by the {} visitor'
                message = message_template.format(node, visitor)
                self.fail(msg=message)
            self.assertIsInstance(
                py_node, ast.expr, msg='Python node is not an expression')

        test('greater-than-word')
        test('operator-word')
        test('word')

    def test_equal_to_word_visitor(self) -> None:
        token = concat.level0.lex.Token()
        token.start = (0, 0)
        node = concat.level1.parse.EqualToWordNode(token)

        def test(visitor: str) -> None:
            try:
                py_node = self.__visitors[visitor].visit(node)
            except concat.visitors.VisitFailureException:
                message_template = '{} was not accepted by the {} visitor'
                message = message_template.format(node, visitor)
                self.fail(msg=message)
            self.assertIsInstance(
                py_node, ast.expr, msg='Python node is not an expression')

        test('equal-to-word')
        test('operator-word')
        test('word')

    def test_greater_than_or_equal_to_word_visitor(self) -> None:
        token = concat.level0.lex.Token()
        token.start = (0, 0)
        node = concat.level1.parse.GreaterThanOrEqualToWordNode(token)

        def test(visitor: str) -> None:
            try:
                py_node = self.__visitors[visitor].visit(node)
            except concat.visitors.VisitFailureException:
                message_template = '{} was not accepted by the {} visitor'
                message = message_template.format(node, visitor)
                self.fail(msg=message)
            self.assertIsInstance(
                py_node, ast.expr, msg='Python node is not an expression')

        test('greater-than-or-equal-to-word')
        test('operator-word')
        test('word')

    def test_less_than_or_equal_to_word_visitor(self) -> None:
        token = concat.level0.lex.Token()
        token.start = (0, 0)
        node = concat.level1.parse.LessThanOrEqualToWordNode(token)

        def test(visitor: str) -> None:
            try:
                py_node = self.__visitors[visitor].visit(node)
            except concat.visitors.VisitFailureException:
                message_template = '{} was not accepted by the {} visitor'
                message = message_template.format(node, visitor)
                self.fail(msg=message)
            self.assertIsInstance(
                py_node, ast.expr, msg='Python node is not an expression')

        test('less-than-or-equal-to-word')
        test('operator-word')
        test('word')

    def test_not_equal_to_word_visitor(self) -> None:
        token = concat.level0.lex.Token()
        token.start = (0, 0)
        node = concat.level1.parse.NotEqualToWordNode(token)

        def test(visitor: str) -> None:
            try:
                py_node = self.__visitors[visitor].visit(node)
            except concat.visitors.VisitFailureException:
                message_template = '{} was not accepted by the {} visitor'
                message = message_template.format(node, visitor)
                self.fail(msg=message)
            self.assertIsInstance(
                py_node, ast.expr, msg='Python node is not an expression')

        test('not-equal-to-word')
        test('operator-word')
        test('word')

    def test_is_word_visitor(self) -> None:
        token = concat.level0.lex.Token()
        token.start = (0, 0)
        node = concat.level1.parse.IsWordNode(token)

        def test(visitor: str) -> None:
            try:
                py_node = self.__visitors[visitor].visit(node)
            except concat.visitors.VisitFailureException:
                message_template = '{} was not accepted by the {} visitor'
                message = message_template.format(node, visitor)
                self.fail(msg=message)
            self.assertIsInstance(
                py_node, ast.expr, msg='Python node is not an expression')

        test('is-word')
        test('operator-word')
        test('word')

    def test_in_word_visitor(self) -> None:
        token = concat.level0.lex.Token()
        token.start = (0, 0)
        node = concat.level1.parse.InWordNode(token)

        def test(visitor: str) -> None:
            try:
                py_node = self.__visitors[visitor].visit(node)
            except concat.visitors.VisitFailureException:
                message_template = '{} was not accepted by the {} visitor'
                message = message_template.format(node, visitor)
                self.fail(msg=message)
            self.assertIsInstance(
                py_node, ast.expr, msg='Python node is not an expression')

        test('in-word')
        test('operator-word')
        test('word')

    def test_or_word_visitor(self) -> None:
        token = concat.level0.lex.Token()
        token.start = (0, 0)
        node = concat.level1.parse.OrWordNode(token)

        def test(visitor: str) -> None:
            try:
                py_node = self.__visitors[visitor].visit(node)
            except concat.visitors.VisitFailureException:
                message_template = '{} was not accepted by the {} visitor'
                message = message_template.format(node, visitor)
                self.fail(msg=message)
            self.assertIsInstance(
                py_node, ast.expr, msg='Python node is not an expression')

        test('or-word')
        test('operator-word')
        test('word')

    def test_and_word_visitor(self) -> None:
        token = concat.level0.lex.Token()
        token.start = (0, 0)
        node = concat.level1.parse.AndWordNode(token)

        def test(visitor: str) -> None:
            try:
                py_node = self.__visitors[visitor].visit(node)
            except concat.visitors.VisitFailureException:
                message_template = '{} was not accepted by the {} visitor'
                message = message_template.format(node, visitor)
                self.fail(msg=message)
            self.assertIsInstance(
                py_node, ast.expr, msg='Python node is not an expression')

        test('and-word')
        test('operator-word')
        test('word')

    def test_not_word_visitor(self) -> None:
        token = concat.level0.lex.Token()
        token.start = (0, 0)
        node = concat.level1.parse.NotWordNode(token)

        def test(visitor: str) -> None:
            try:
                py_node = self.__visitors[visitor].visit(node)
            except concat.visitors.VisitFailureException:
                message_template = '{} was not accepted by the {} visitor'
                message = message_template.format(node, visitor)
                self.fail(msg=message)
            self.assertIsInstance(
                py_node, ast.expr, msg='Python node is not an expression')

        test('not-word')
        test('operator-word')
        test('word')

    def test_assert_word_visitor(self) -> None:
        token = concat.level0.lex.Token()
        token.start = (0, 0)
        node = concat.level1.parse.AssertWordNode(token)

        def test(visitor: str) -> None:
            try:
                py_node = self.__visitors[visitor].visit(node)
            except concat.visitors.VisitFailureException:
                message_template = '{} was not accepted by the {} visitor'
                message = message_template.format(node, visitor)
                self.fail(msg=message)
            self.assertIsInstance(
                py_node, ast.expr, msg='Python node is not an expression')

        test('assert-word')
        test('word')

    def test_raise_word_visitor(self) -> None:
        token = concat.level0.lex.Token()
        token.start = (0, 0)
        node = concat.level1.parse.RaiseWordNode(token)

        def test(visitor: str) -> None:
            try:
                py_node = self.__visitors[visitor].visit(node)
            except concat.visitors.VisitFailureException:
                message_template = '{} was not accepted by the {} visitor'
                message = message_template.format(node, visitor)
                self.fail(msg=message)
            self.assertIsInstance(
                py_node, ast.expr, msg='Python node is not an expression')

        test('raise-word')
        test('word')
