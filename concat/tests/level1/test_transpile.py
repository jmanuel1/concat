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

    def _test_visitor_basic(
            self, node: concat.level0.parse.Node, visitor: str) -> ast.AST:
        try:
            py_node = self.__visitors[visitor].visit(node)
        except concat.visitors.VisitFailureException:
            message = '{} was not accepted by the {} visitor'.format(
                node, visitor)
            self.fail(msg=message)
        self.assertIsInstance(
            py_node, ast.Call, msg='Python node is not a call')
        return py_node

    def test_none_word_visitor(self) -> None:
        """Tests that none words are transpiled to calls which contain None."""
        none = Token()
        none.start = (0, 0)
        node = concat.level1.parse.NoneWordNode(none)
        py_node = self._test_visitor_basic(node, 'none-word')
        value = cast(ast.NameConstant, cast(ast.Call, py_node).args[0]).value
        self.assertIs(value, None,
                      msg='Python None node does not contain `None`')

    def test_not_impl_word_visitor(self) -> None:
        """Not-impl words are transpiled to calls containing NotImplemented."""
        not_impl = Token()
        not_impl.start = (0, 0)
        node = concat.level1.parse.NotImplWordNode(not_impl)
        py_node = self._test_visitor_basic(node, 'not-impl-word')
        identifier = cast(ast.Name, cast(ast.Call, py_node).args[0]).id
        message = 'Python Name node does not contain "NotImplemented"'
        self.assertEqual(identifier, 'NotImplemented', msg=message)

    def test_ellipsis_word_visitor(self) -> None:
        """Ellipsis words are transpiled to calls which contain '...'."""
        ellipsis = Token()
        ellipsis.start = (0, 0)
        node = concat.level1.parse.EllipsisWordNode(ellipsis)
        py_node = self._test_visitor_basic(node, 'ellipsis-word')
        message = 'The Python node within the call is not an Ellipsis'
        self.assertIsInstance(
            cast(ast.Call, py_node).args[0], ast.Ellipsis, msg=message)

    def test_slice_word_visitor_with_step(self) -> None:
        two_token = concat.level0.lex.Token()
        two_token.type, two_token.value = 'NUMBER', '2'
        two = concat.level0.parse.NumberWordNode(two_token)
        node = concat.level1.parse.SliceWordNode(([], [], [two]))
        try:
            py_node = self.__visitors['slice-word'].visit(node)
        except concat.visitors.VisitFailureException:
            message_template = '{} was not accepted by the slice-word visitor'
            message = message_template.format(node)
            self.fail(msg=message)
        self.assertIn('2', astunparse.unparse(py_node),
                      msg='Python node does not contain 2')

    def test_del_statement_visitor(self) -> None:
        """Concat del statements are transpiled to Python del statements."""
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

    def test_async_funcdef_statement_visitor(self) -> None:
        """Async function definitions are transpiled to the same kind of Python statement."""
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
        """Function definitions are transpiled to the same kind of Python statement."""
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

    def test_import_statement_visitor_with_as(self) -> None:
        """import ... as ... statements are transpiled to the same kind of Python statement.

        The as-clause will be present in the resulting Python AST."""

        node = concat.level1.parse.ImportStatementNode('a.submodule', 'b')

        def test(visitor: str) -> None:
            try:
                py_node = self.__visitors[visitor].visit(node)
            except concat.visitors.VisitFailureException:
                message_template = '{} was not accepted by the {} visitor'
                message = message_template.format(node, visitor)
                self.fail(msg=message)
            # The transpiler wraps its output in an if, so don't test for
            # ast.Import
            self.assertIsInstance(
                py_node, ast.stmt, msg='Python node is not a statement')
            self.assertIn('as b', astunparse.unparse(py_node),
                          msg='as-part was not transpiled')

        test('import-statement')
        test('statement')

    def test_import_statement_visitor_with_from(self) -> None:
        node = concat.level1.parse.FromImportStatementNode('a.submodule', 'b')

        def test(visitor: str) -> None:
            try:
                py_node = self.__visitors[visitor].visit(node)
            except concat.visitors.VisitFailureException:
                message_template = '{} was not accepted by the {} visitor'
                message = message_template.format(node, visitor)
                self.fail(msg=message)
            # The transpiler wraps its output in an if, so don't test for
            # ast.Import
            self.assertIsInstance(
                py_node, ast.stmt,
                msg='Python node is not a statement')
            self.assertIn('from', astunparse.unparse(py_node),
                          msg='was not transpiled as from-import')

        test('import-statement')
        test('statement')

    def test_import_statement_visitor_with_from_and_as(self) -> None:
        node = concat.level1.parse.FromImportStatementNode(
            'a.submodule', 'b', 'c')

        def test(visitor: str) -> None:
            try:
                py_node = self.__visitors[visitor].visit(node)
            except concat.visitors.VisitFailureException:
                message_template = '{} was not accepted by the {} visitor'
                message = message_template.format(node, visitor)
                self.fail(msg=message)
            # The transpiler wraps its output in an if, so don't test for
            # ast.Import
            self.assertIsInstance(
                py_node, ast.stmt,
                msg='Python node is not a statement')
            self.assertIn('from', astunparse.unparse(py_node),
                          msg='was not transpiled as from-import')
            self.assertIn('as c', astunparse.unparse(py_node),
                          msg='as-part was not transpiled')

        test('import-statement')
        test('statement')

    def test_import_statement_visitor_with_from_and_star(self) -> None:
        node = concat.level1.parse.FromImportStarStatementNode('a')

        def test(visitor: str) -> None:
            try:
                py_node = self.__visitors[visitor].visit(node)
            except concat.visitors.VisitFailureException:
                message_template = '{} was not accepted by the {} visitor'
                message = message_template.format(node, visitor)
                self.fail(msg=message)
            # The transpiler wraps its output in an if, so don't test for
            # ast.Import
            self.assertIsInstance(
                py_node, ast.stmt,
                msg='Python node is not a statement')
            self.assertIn('from', astunparse.unparse(py_node),
                          msg='was not transpiled as from-import')
            self.assertIn('*', astunparse.unparse(py_node),
                          msg='star-part was not transpiled')

        test('import-statement')
        test('statement')

    def test_classdef_statement_visitor(self) -> None:
        node = concat.level1.parse.ClassdefStatementNode('A', [], (0, 0))

        def test(visitor: str) -> None:
            try:
                py_node = self.__visitors[visitor].visit(node)
            except concat.visitors.VisitFailureException:
                message_template = '{} was not accepted by the {} visitor'
                message = message_template.format(node, visitor)
                self.fail(msg=message)
            self.assertIsInstance(
                py_node,
                ast.ClassDef,
                msg='Python node is not a class definition')

        test('classdef-statement')
        test('statement')

    def test_classdef_statement_visitor_with_decorators(self) -> None:
        name = Token()
        name.start, name.value = (0, 0), 'decorator'
        decorator = concat.level0.parse.NameWordNode(name)
        node = concat.level1.parse.ClassdefStatementNode(
            'A', [], (0, 0), [decorator])

        def test(visitor: str) -> None:
            try:
                py_node = self.__visitors[visitor].visit(node)
            except concat.visitors.VisitFailureException:
                message_template = '{} was not accepted by the {} visitor'
                message = message_template.format(node, visitor)
                self.fail(msg=message)
            self.assertIsInstance(
                py_node,
                ast.ClassDef,
                msg='Python node is not a class definition')
            self.assertIn('@', astunparse.unparse(py_node),
                          msg='decorator was not transpiled')

        test('classdef-statement')
        test('statement')

    def test_classdef_statement_visitor_with_bases(self) -> None:
        name = Token()
        name.start, name.value = (0, 0), 'base'
        base = concat.level0.parse.NameWordNode(name)
        node = concat.level1.parse.ClassdefStatementNode(
            'A', [], (0, 0), [], [[base]])

        def test(visitor: str) -> None:
            try:
                py_node = self.__visitors[visitor].visit(node)
            except concat.visitors.VisitFailureException:
                message_template = '{} was not accepted by the {} visitor'
                message = message_template.format(node, visitor)
                self.fail(msg=message)
            self.assertIsInstance(
                py_node,
                ast.ClassDef,
                msg='Python node is not a class definition')
            self.assertIn('(', astunparse.unparse(py_node),
                          msg='bases were not transpiled')
            self.assertIn('base', astunparse.unparse(py_node),
                          msg='bases were not transpiled')

        test('classdef-statement')
        test('statement')

    def test_classdef_statement_visitor_with_keyword_args(self) -> None:
        name = Token()
        name.start, name.value = (0, 0), 'meta'
        word = concat.level0.parse.NameWordNode(name)
        node = concat.level1.parse.ClassdefStatementNode(
            'A', [], (0, 0), [], [], [('metaclass', word)])

        def test(visitor: str) -> None:
            try:
                py_node = self.__visitors[visitor].visit(node)
            except concat.visitors.VisitFailureException:
                message_template = '{} was not accepted by the {} visitor'
                message = message_template.format(node, visitor)
                self.fail(msg=message)
            self.assertIsInstance(
                py_node,
                ast.ClassDef,
                msg='Python node is not a class definition')
            self.assertIn('(', astunparse.unparse(py_node),
                          msg='keyword arguments were not transpiled')
            self.assertIn('metaclass=', astunparse.unparse(
                py_node), msg='keyword arguments were not transpiled')

        test('classdef-statement')
        test('statement')


class TestMagicMethodTranspilaton(unittest.TestCase):
    """Test that magic methods are transformed into what Python expects.

    Note that we don't transform module-level __getattr__ and __dict__, or
    handle __(mro_entries, class_getitem)__ since those are Python 3.7
    features. We don't handle __set_name__ either, since that was addded in
    3.6.

    Special names that aren't methods, like __slots__ aren't accounted for. We
    don't even have assignment!"""

    def setUp(self) -> None:
        self.__visitors = concat.visitors.VisitorDict[
            concat.level0.parse.Node, ast.AST]()
        self.__visitors.extend_with(concat.level0.transpile.level_0_extension)
        self.__visitors.extend_with(concat.level1.transpile.level_1_extension)

    def test__new__(self) -> None:
        """Test that transpiled __new__ methods take the class, stack, and stash.

        def __new__ should become def __new__(cls, stack, stash) and it should push cls onto the stack before executing the rest of the function."""
        name = Token()
        name.start, name.value = (0, 0), '__new__'
        new_def = concat.level1.parse.FuncdefStatementNode(
            name, [], None, [], (0, 0))
        node = concat.level1.parse.ClassdefStatementNode(
            'A', [new_def], (0, 0), [], [])
        py_node = cast(
            ast.ClassDef, self.__visitors['classdef-statement'].visit(node))
        py_new_def = cast(ast.FunctionDef, py_node.body[0])
        py_args = [arg.arg for arg in py_new_def.args.args]
        self.assertEqual(
            py_args, ['cls', 'stack', 'stash'], msg='wrong arguments')
        py_first_statement = py_new_def.body[0]
        self.assertIn('stack.append(cls)', astunparse.unparse(
            py_first_statement), msg="doesn't push cls")

    def test_instance_functions_with_concat_signatures(self) -> None:
        """Test that transpiled __(init, call)__ methods take self, the stack, and the stash.

        For example, def __init__ should become def __init__(self, stack, stash) and it should push self onto the stack before executing the rest of the function. The function need not return a value other than None."""
        for method in {'init', 'call'}:
            with self.subTest(msg='testing __{}__'.format(method), method=method):
                name = Token()
                name.start, name.value = (0, 0), '__{}__'.format(method)
                method_def = concat.level1.parse.FuncdefStatementNode(
                    name, [], None, [], (0, 0))
                node = concat.level1.parse.ClassdefStatementNode(
                    'A', [method_def], (0, 0), [], [])
                visitor = self.__visitors['classdef-statement']
                py_node = cast(ast.ClassDef, visitor.visit(node))
                py_method_def = cast(ast.FunctionDef, py_node.body[0])
                py_args = [arg.arg for arg in py_method_def.args.args]
                self.assertEqual(
                    py_args, ['self', 'stack', 'stash'], msg='wrong arguments')
                py_first_statement = py_method_def.body[0]
                self.assertIn('stack.append(self)', astunparse.unparse(
                    py_first_statement), msg="doesn't push self")

    def test_self_only_methods(self) -> None:
        """Test that transpiled __(del, repr, etc.)__ methods take only self.

        For example, def __del__ should become def __del__(self) and it should
        push self onto the stack before executing the rest of the function.
        Then, it should return stack.pop()."""
        for method in {'del', 'repr', 'str', 'bytes', 'hash', 'bool', 'dir',
                       'len', 'length_hint', 'aenter', 'anext', 'aiter',
                       'await', 'enter', 'ceil', 'floor', 'trunc', 'index',
                       'float', 'int', 'complex', 'invert', 'abs', 'pos',
                       'neg', 'reversed', 'iter'}:
            method_name = '__{}__'.format(method)
            with self.subTest(msg='testing {}'.format(method_name),
                              method=method_name):
                name = Token()
                name.start, name.value = (0, 0), method_name
                defun = concat.level1.parse.FuncdefStatementNode(
                    name, [], None, [], (0, 0))
                node = concat.level1.parse.ClassdefStatementNode(
                    'A', [defun], (0, 0), [], [])
                visitor = self.__visitors['classdef-statement']
                py_node = cast(ast.ClassDef, visitor.visit(node))
                py_def = cast(ast.FunctionDef, py_node.body[0])
                py_args = [arg.arg for arg in py_def.args.args]
                self.assertEqual(py_args, ['self'], msg='wrong arguments')
                py_first_statement = py_def.body[0]
                self.assertIn('stack.append(self)', astunparse.unparse(
                    py_first_statement), msg="doesn't push self")
                py_last_statement = py_def.body[-1]
                message = "doesn't pop return value off stack"
                self.assertIn('return stack.pop()', astunparse.unparse(
                    py_last_statement), msg=message)

    def test__format__(self) -> None:
        """Test that transpiled __format__ methods take only self and format_spec.

        def __format__ should become def __format__(self, format_spec) and it should push format_spec and self onto the stack before executing the rest of the function. The function should return stack.pop()."""
        name = Token()
        name.start, name.value = (0, 0), '__format__'
        format_def = concat.level1.parse.FuncdefStatementNode(
            name, [], None, [], (0, 0))
        node = concat.level1.parse.ClassdefStatementNode(
            'A', [format_def], (0, 0), [], [])
        py_node = cast(
            ast.ClassDef, self.__visitors['classdef-statement'].visit(node))
        py_format_def = cast(ast.FunctionDef, py_node.body[0])
        py_args = [arg.arg for arg in py_format_def.args.args]
        self.assertEqual(
            py_args, ['self', 'format_spec'], msg='wrong arguments')
        py_first_statement, py_second_statement = py_format_def.body[0:2]
        self.assertIn('stack.append(format_spec)', astunparse.unparse(
            py_first_statement), msg="doesn't push format_spec")
        self.assertIn('stack.append(self)', astunparse.unparse(
            py_second_statement), msg="doesn't push self")
        py_last_statement = py_format_def.body[-1]
        self.assertIn('return stack.pop()', astunparse.unparse(
            py_last_statement), msg="doesn't pop return value off stack")

    def test_comparisons_and_augmented_assignments(self) -> None:
        """Test that transpiled comparison/augmented assignment methods take only self and other.

        For example, def __lt__ should become def __lt__(self, other) and it should push self and other onto the stack before executing the rest of the function. The function should return stack.pop().

        __ipow__ is not tested here; it has a different signature."""
        for method in {'lt', 'le', 'eq', 'ne', 'gt', 'ge', 'ior', 'ixor',
                       'iand', 'irshift', 'ilshift', 'imod', 'ifloordiv',
                       'itruediv', 'imatmul', 'imul', 'isub', 'iadd', 'ror',
                       'rxor', 'rand', 'rrshift', 'rlshift', 'rmod',
                       'rfloordiv', 'rtruediv', 'rmatmul', 'rmul', 'rsub',
                       'radd', 'rpow', 'or', 'xor',
                       'and', 'rshift', 'lshift', 'mod', 'floordiv',
                       'truediv', 'matmul', 'mul', 'sub', 'add'}:
            with self.subTest(msg='testing __{}__'.format(method), method=method):
                name = Token()
                name.start, name.value = (0, 0), '__{}__'.format(method)
                defun = concat.level1.parse.FuncdefStatementNode(
                    name, [], None, [], (0, 0))
                node = concat.level1.parse.ClassdefStatementNode(
                    'A', [defun], (0, 0), [], [])
                py_node = cast(
                    ast.ClassDef, self.__visitors['classdef-statement'].visit(node))
                py_def = cast(ast.FunctionDef, py_node.body[0])
                py_args = [arg.arg for arg in py_def.args.args]
                self.assertEqual(
                    py_args, ['self', 'other'], msg='wrong arguments')
                py_first_statement, py_second_statement = py_def.body[0:2]
                self.assertIn('stack.append(self)', astunparse.unparse(
                    py_first_statement), msg="doesn't push self")
                self.assertIn('stack.append(other)', astunparse.unparse(
                    py_second_statement), msg="doesn't push other")
                py_last_statement = py_def.body[-1]
                self.assertIn('return stack.pop()', astunparse.unparse(
                    py_last_statement), msg="doesn't pop return value off stack")

    def test_attribute_methods_except_setattr_and_dir(self) -> None:
        """Test that transpiled __(getattr, getattribute, etc.)__ methods take only self and name.

        For example, def __getattr__ should become def __getattr__(self, name) and it should push name and self onto the stack before executing the rest of the function. The function should return stack.pop()."""
        for method in {'getattr', 'getattribute', 'delattr'}:
            with self.subTest(msg='testing __{}__'.format(method), method=method):
                name = Token()
                name.start, name.value = (0, 0), '__{}__'.format(method)
                getattr_def = concat.level1.parse.FuncdefStatementNode(
                    name, [], None, [], (0, 0))
                node = concat.level1.parse.ClassdefStatementNode(
                    'A', [getattr_def], (0, 0), [], [])
                py_node = cast(
                    ast.ClassDef, self.__visitors['classdef-statement'].visit(node))
                py_getattr_def = cast(ast.FunctionDef, py_node.body[0])
                py_args = [arg.arg for arg in py_getattr_def.args.args]
                self.assertEqual(
                    py_args, ['self', 'name'], msg='wrong arguments')
                py_first_statement, py_second_statement = py_getattr_def.body[0:2]
                self.assertIn('stack.append(name)', astunparse.unparse(
                    py_first_statement), msg="doesn't push name")
                self.assertIn('stack.append(self)', astunparse.unparse(
                    py_second_statement), msg="doesn't push self")
                py_last_statement = py_getattr_def.body[-1]
                self.assertIn('return stack.pop()', astunparse.unparse(
                    py_last_statement), msg="doesn't pop return value off stack")

    def test__setattr__(self) -> None:
        """Test that transpiled __setattr__ methods take only self, name, and value.

        def __setattr__ should become def __setattr__(self, name, value) and it should push value, name, and self onto the stack before executing the rest of the function. The function should return stack.pop()."""
        name = Token()
        name.start, name.value = (0, 0), '__setattr__'
        setattr_def = concat.level1.parse.FuncdefStatementNode(
            name, [], None, [], (0, 0))
        node = concat.level1.parse.ClassdefStatementNode(
            'A', [setattr_def], (0, 0), [], [])
        py_node = cast(
            ast.ClassDef, self.__visitors['classdef-statement'].visit(node))
        py_setattr_def = cast(ast.FunctionDef, py_node.body[0])
        py_args = [arg.arg for arg in py_setattr_def.args.args]
        self.assertEqual(
            py_args, ['self', 'name', 'value'], msg='wrong arguments')
        py_first_statement = py_setattr_def.body[0:2]
        self.assertIn('stack += [value, name, self]', astunparse.unparse(
            py_first_statement), msg="doesn't push value, name, and self")
        py_last_statement = py_setattr_def.body[-1]
        self.assertIn('return stack.pop()', astunparse.unparse(
            py_last_statement), msg="doesn't pop return value off stack")

    def test__get__(self) -> None:
        """Test that transpiled __get__ methods take only self, instance, and owner.

        def __get__ should become def __get__(self, instance, owner) and it should push owner, instance, and self onto the stack before executing the rest of the function. The function should return stack.pop()."""
        name = Token()
        name.start, name.value = (0, 0), '__get__'
        get_def = concat.level1.parse.FuncdefStatementNode(
            name, [], None, [], (0, 0))
        node = concat.level1.parse.ClassdefStatementNode(
            'A', [get_def], (0, 0), [], [])
        py_node = cast(
            ast.ClassDef, self.__visitors['classdef-statement'].visit(node))
        py_get_def = cast(ast.FunctionDef, py_node.body[0])
        py_args = [arg.arg for arg in py_get_def.args.args]
        self.assertEqual(
            py_args, ['self', 'instance', 'owner'], msg='wrong arguments')
        py_first_statement = py_get_def.body[0:2]
        self.assertIn('stack += [owner, instance, self]', astunparse.unparse(
            py_first_statement), msg="doesn't push owner, instance, and self")
        py_last_statement = py_get_def.body[-1]
        self.assertIn('return stack.pop()', astunparse.unparse(
            py_last_statement), msg="doesn't pop return value off stack")

    def test__set__(self) -> None:
        """Test that transpiled __set__ methods take only self, instance, and value.

        def __set__ should become def __set__(self, instance, value) and it should push value, instance, and self onto the stack before executing the rest of the function. The function should return stack.pop()."""
        name = Token()
        name.start, name.value = (0, 0), '__set__'
        set_def = concat.level1.parse.FuncdefStatementNode(
            name, [], None, [], (0, 0))
        node = concat.level1.parse.ClassdefStatementNode(
            'A', [set_def], (0, 0), [], [])
        py_node = cast(
            ast.ClassDef, self.__visitors['classdef-statement'].visit(node))
        py_set_def = cast(ast.FunctionDef, py_node.body[0])
        py_args = [arg.arg for arg in py_set_def.args.args]
        self.assertEqual(
            py_args, ['self', 'instance', 'value'], msg='wrong arguments')
        py_first_statement = py_set_def.body[0:2]
        self.assertIn('stack += [value, instance, self]', astunparse.unparse(
            py_first_statement), msg="doesn't push value, instance, and self")
        py_last_statement = py_set_def.body[-1]
        self.assertIn('return stack.pop()', astunparse.unparse(
            py_last_statement), msg="doesn't pop return value off stack")

    def test_methods_taking_self_and_instance(self) -> None:
        """Test that transpiled __(delete, instancecheck)__ methods take only self and instance.

        For example, def __delete__ should become def __delete__(self, instance) and it should push instance and self onto the stack before executing the rest of the function. The function should return stack.pop()."""
        for method in {'delete', 'instancecheck'}:
            with self.subTest(msg='testing __{}__'.format(method), method=method):
                name = Token()
                name.start, name.value = (0, 0), '__{}__'.format(method)
                defun = concat.level1.parse.FuncdefStatementNode(
                    name, [], None, [], (0, 0))
                node = concat.level1.parse.ClassdefStatementNode(
                    'A', [defun], (0, 0), [], [])
                py_node = cast(
                    ast.ClassDef, self.__visitors['classdef-statement'].visit(node))
                py_defun = cast(ast.FunctionDef, py_node.body[0])
                py_args = [arg.arg for arg in py_defun.args.args]
                self.assertEqual(
                    py_args, ['self', 'instance'], msg='wrong arguments')
                py_first_statement = py_defun.body[0:2]
                self.assertIn('stack += [instance, self]', astunparse.unparse(
                    py_first_statement), msg="doesn't push instance and self")
                py_last_statement = py_defun.body[-1]
                self.assertIn('return stack.pop()', astunparse.unparse(
                    py_last_statement), msg="doesn't pop return value off stack")

    def test__init_subclass__(self) -> None:
        """Test that transpiled __init_subclass__ methods take only cls and arbitrary keyword arguments.

        def __init_subclass__ should become def __init_subclass__(cls, **kwargs) and it should push kwargs and self onto the stack before executing the rest of the function. The function should return stack.pop()."""
        name = Token()
        name.start, name.value = (0, 0), '__init_subclass__'
        init_subclass_def = concat.level1.parse.FuncdefStatementNode(
            name, [], None, [], (0, 0))
        node = concat.level1.parse.ClassdefStatementNode(
            'A', [init_subclass_def], (0, 0), [], [])
        py_node = cast(
            ast.ClassDef, self.__visitors['classdef-statement'].visit(node))
        py_init_subclass_def = cast(ast.FunctionDef, py_node.body[0])
        py_args = [arg.arg for arg in py_init_subclass_def.args.args]
        self.assertEqual(py_args, ['cls'], msg='wrong positonal arguments')
        py_kwarg_object = py_init_subclass_def.args.kwarg
        self.assertIsNotNone(py_kwarg_object, msg='no ** argument')
        py_kwarg = cast(ast.arg, py_kwarg_object).arg
        self.assertEqual(py_kwarg, 'kwargs', msg='wrong ** argument')
        py_first_statement = py_init_subclass_def.body[0:2]
        self.assertIn('stack += [kwargs, self]', astunparse.unparse(
            py_first_statement), msg="doesn't push kwargs and self")
        py_last_statement = py_init_subclass_def.body[-1]
        self.assertIn('return stack.pop()', astunparse.unparse(
            py_last_statement), msg="doesn't pop return value off stack")

    def test__prepare__(self) -> None:
        """Test that transpiled __prepare__ methods take only cls, bases, and arbitrary keyword arguments.

        def __prepare__ should become def __prepare__(cls, name, bases, **kwds) and it should push kwds, bases, name, and self onto the stack before executing the rest of the function. The function should return stack.pop(). It is up to the programmer to decorate the function with @classmethod."""
        name = Token()
        name.start, name.value = (0, 0), '__prepare__'
        prepare_def = concat.level1.parse.FuncdefStatementNode(
            name, [], None, [], (0, 0))
        node = concat.level1.parse.ClassdefStatementNode(
            'A', [prepare_def], (0, 0), [], [])
        py_node = cast(
            ast.ClassDef, self.__visitors['classdef-statement'].visit(node))
        py_prepare_def = cast(ast.FunctionDef, py_node.body[0])
        py_args = [arg.arg for arg in py_prepare_def.args.args]
        self.assertEqual(py_args, ['cls', 'name', 'bases'],
                         msg='wrong positonal arguments')
        py_kwarg_object = py_prepare_def.args.kwarg
        self.assertIsNotNone(py_kwarg_object, msg='no ** argument')
        py_kwarg = cast(ast.arg, py_kwarg_object).arg
        self.assertEqual(py_kwarg, 'kwds', msg='wrong ** argument')
        py_first_statement = py_prepare_def.body[0:2]
        self.assertIn('stack += [kwds, bases, name, cls]', astunparse.unparse(
            py_first_statement), msg="doesn't push kwds, bases, name, and cls")
        py_last_statement = py_prepare_def.body[-1]
        self.assertIn('return stack.pop()', astunparse.unparse(
            py_last_statement), msg="doesn't pop return value off stack")

    def test__subclasscheck__(self) -> None:
        """Test that transpiled __subclasscheck__ methods take only self and subclass.

        def __subclasscheck__ should become def __subclasscheck__(self, subclass) and it should push subclass and self onto the stack before executing the rest of the function. The function should return stack.pop()."""
        name = Token()
        name.start, name.value = (0, 0), '__subclasscheck__'
        subclasscheck_def = concat.level1.parse.FuncdefStatementNode(
            name, [], None, [], (0, 0))
        node = concat.level1.parse.ClassdefStatementNode(
            'A', [subclasscheck_def], (0, 0), [], [])
        py_node = cast(
            ast.ClassDef, self.__visitors['classdef-statement'].visit(node))
        py_subclasscheck_def = cast(ast.FunctionDef, py_node.body[0])
        py_args = [arg.arg for arg in py_subclasscheck_def.args.args]
        self.assertEqual(py_args, ['self', 'subclass'],
                         msg='wrong positonal arguments')
        py_first_statement = py_subclasscheck_def.body[0:2]
        self.assertIn('stack += [subclass, self]', astunparse.unparse(
            py_first_statement), msg="doesn't push subclass and self")
        py_last_statement = py_subclasscheck_def.body[-1]
        self.assertIn('return stack.pop()', astunparse.unparse(
            py_last_statement), msg="doesn't pop return value off stack")

    def test_key_related_methods(self) -> None:
        """Test that transpiled __(getitem, missing, etc.)__ methods take only self and key.

        For example, def __getitem__ should become def __getitem__(self, key) and it should push key and self onto the stack before executing the rest of the function. The function should return stack.pop().

        Note: __setitem__ has a different signature."""
        for method in {'getitem', 'missing', 'delitem'}:
            method_name = '__{}__'.format(method)
            with self.subTest(msg='testing {}'.format(method_name), method_name=method_name):
                name = Token()
                name.start, name.value = (0, 0), method_name
                method_def = concat.level1.parse.FuncdefStatementNode(
                    name, [], None, [], (0, 0))
                node = concat.level1.parse.ClassdefStatementNode(
                    'A', [method_def], (0, 0), [], [])
                py_node = cast(
                    ast.ClassDef, self.__visitors['classdef-statement'].visit(node))
                py_method_def = cast(ast.FunctionDef, py_node.body[0])
                py_args = [arg.arg for arg in py_method_def.args.args]
                self.assertEqual(py_args, ['self', 'key'],
                                 msg='wrong positonal arguments')
                py_first_statement = py_method_def.body[0:2]
                self.assertIn('stack += [key, self]', astunparse.unparse(
                    py_first_statement), msg="doesn't push subclass and self")
                py_last_statement = py_method_def.body[-1]
                self.assertIn('return stack.pop()', astunparse.unparse(
                    py_last_statement), msg="doesn't pop return value off stack")

    def test_context_manager_exit_methods(self) -> None:
        """Test that transpiled __(aexit, exit)__ methods take only self, exc_type, exc_value, and traceback.

        For example, def __aexit__ should become def __aexit__(self, exc_type, exc_value, traceback) and it should push traceback, exc_value, exc_type, and self onto the stack before executing the rest of the function. The function should return stack.pop()."""
        for method in {'exit', 'aexit'}:
            method_name = '__{}__'.format(method)
            with self.subTest(msg='testing {}'.format(method_name), method_name=method_name):
                name = Token()
                name.start, name.value = (0, 0), method_name
                method_def = concat.level1.parse.FuncdefStatementNode(
                    name, [], None, [], (0, 0))
                node = concat.level1.parse.ClassdefStatementNode(
                    'A', [method_def], (0, 0), [], [])
                py_node = cast(
                    ast.ClassDef, self.__visitors['classdef-statement'].visit(node))
                py_method_def = cast(ast.FunctionDef, py_node.body[0])
                py_args = [arg.arg for arg in py_method_def.args.args]
                self.assertEqual(py_args, [
                                 'self', 'exc_type', 'exc_value', 'traceback'], msg='wrong positonal arguments')
                py_first_statement = py_method_def.body[0:2]
                self.assertIn('stack += [traceback, exc_value, exc_type, self]', astunparse.unparse(
                    py_first_statement), msg="doesn't push traceback, exc_value, exc_type, and self")
                py_last_statement = py_method_def.body[-1]
                self.assertIn('return stack.pop()', astunparse.unparse(
                    py_last_statement), msg="doesn't pop return value off stack")

    def test__round__(self) -> None:
        """Test that transpiled __round__ methods take only self and ndigits.

        def __round__ should become def __round__(self, ndigits) and it should push ndigits and self onto the stack before executing the rest of the function. The function should return stack.pop()."""
        name = Token()
        name.start, name.value = (0, 0), '__round__'
        method_def = concat.level1.parse.FuncdefStatementNode(
            name, [], None, [], (0, 0))
        node = concat.level1.parse.ClassdefStatementNode(
            'A', [method_def], (0, 0), [], [])
        py_node = cast(
            ast.ClassDef, self.__visitors['classdef-statement'].visit(node))
        py_method_def = cast(ast.FunctionDef, py_node.body[0])
        py_args = [arg.arg for arg in py_method_def.args.args]
        self.assertEqual(py_args, ['self', 'ndigits'],
                         msg='wrong positonal arguments')
        py_first_statement = py_method_def.body[0:2]
        self.assertIn('stack += [ndigits, self]', astunparse.unparse(
            py_first_statement), msg="doesn't push subclass and self")
        py_last_statement = py_method_def.body[-1]
        self.assertIn('return stack.pop()', astunparse.unparse(
            py_last_statement), msg="doesn't pop return value off stack")

    def test_pow(self) -> None:
        """Test that transpiled __[i]pow__ methods take only self, other, and modulo.

        def __[i]pow__ should become def __[i]pow__(self, other, modulo=1) and it should push self, other, and modulo onto the stack before executing the rest of the function. The function should return stack.pop()."""
        for method in {'pow', 'ipow'}:
            method_name = '__{}__'.format(method)
            with self.subTest(msg='testing {}'.format(method_name), method_name=method_name):
                name = Token()
                name.start, name.value = (0, 0), method_name
                method_def = concat.level1.parse.FuncdefStatementNode(
                    name, [], None, [], (0, 0))
                node = concat.level1.parse.ClassdefStatementNode(
                    'A', [method_def], (0, 0), [], [])
                py_node = cast(
                    ast.ClassDef, self.__visitors['classdef-statement'].visit(node))
                py_method_def = cast(ast.FunctionDef, py_node.body[0])
                py_args = [arg.arg for arg in py_method_def.args.args]
                self.assertEqual(py_args, ['self', 'other', 'modulo'],
                                 msg='wrong positonal arguments')
                self.assertIsInstance(
                    py_method_def.args.defaults[-1], ast.Num, msg='modulo default is not a number')
                self.assertEqual(
                    cast(ast.Num, py_method_def.args.defaults[-1]).n, 1, msg='wrong modulo default')
                py_first_statement = py_method_def.body[0:2]
                self.assertIn('stack += [self, other, modulo]', astunparse.unparse(
                    py_first_statement), msg="doesn't push self, other, modulo")
                py_last_statement = py_method_def.body[-1]
                self.assertIn('return stack.pop()', astunparse.unparse(
                    py_last_statement), msg="doesn't pop return value off stack")

    def test__contains__(self) -> None:
        """Test that transpiled __contains__ methods take only self and item.

        def __contains__ should become def __contains__(self, item) and it should push item and self onto the stack before executing the rest of the function. The function should return stack.pop()."""
        name = Token()
        name.start, name.value = (0, 0), '__contains__'
        method_def = concat.level1.parse.FuncdefStatementNode(
            name, [], None, [], (0, 0))
        node = concat.level1.parse.ClassdefStatementNode(
            'A', [method_def], (0, 0), [], [])
        py_node = cast(
            ast.ClassDef, self.__visitors['classdef-statement'].visit(node))
        py_method_def = cast(ast.FunctionDef, py_node.body[0])
        py_args = [arg.arg for arg in py_method_def.args.args]
        self.assertEqual(py_args, ['self', 'item'],
                         msg='wrong positonal arguments')
        py_first_statement = py_method_def.body[0:2]
        self.assertIn('stack += [item, self]', astunparse.unparse(
            py_first_statement), msg="doesn't push item and self")
        py_last_statement = py_method_def.body[-1]
        self.assertIn('return stack.pop()', astunparse.unparse(
            py_last_statement), msg="doesn't pop return value off stack")

    def test__setitem__(self) -> None:
        """Test that transpiled __setitem__ methods take only self, key, and value.

        def __setitem__ should become def __setitem__(self, key, value) and it should push value, key, and self onto the stack before executing the rest of the function. The function should return stack.pop()."""
        name = Token()
        name.start, name.value = (0, 0), '__setitem__'
        method_def = concat.level1.parse.FuncdefStatementNode(
            name, [], None, [], (0, 0))
        node = concat.level1.parse.ClassdefStatementNode(
            'A', [method_def], (0, 0), [], [])
        py_node = cast(
            ast.ClassDef, self.__visitors['classdef-statement'].visit(node))
        py_method_def = cast(ast.FunctionDef, py_node.body[0])
        py_args = [arg.arg for arg in py_method_def.args.args]
        self.assertEqual(py_args, ['self', 'key', 'value'],
                         msg='wrong positonal arguments')
        py_first_statement = py_method_def.body[0:2]
        self.assertIn('stack += [value, key, self]', astunparse.unparse(
            py_first_statement), msg="doesn't push value, key, and self")
        py_last_statement = py_method_def.body[-1]
        self.assertIn('return stack.pop()', astunparse.unparse(
            py_last_statement), msg="doesn't pop return value off stack")
