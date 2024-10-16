import concat.visitors
from concat.lex import Token
import concat.parse
import concat.transpile
from concat.typecheck import StackEffectTypeNode, TypeSequenceNode
import unittest
import ast
from typing import Iterable, Iterator, Type
import astunparse  # type: ignore


class TestSubVisitors(unittest.TestCase):
    def setUp(self) -> None:
        self.__visitors = concat.visitors.VisitorDict[
            concat.parse.Node, ast.AST
        ]()
        self.__visitors.extend_with(concat.transpile.extension)

    def _test_visitor(
        self,
        node: concat.parse.Node,
        visitor: str,
        py_node_type: Type[ast.AST],
    ) -> ast.AST:
        try:
            py_node = self.__visitors[visitor].visit(node)
        except concat.visitors.VisitFailureException:
            message_template = '{} was not accepted by the {} visitor'
            message = message_template.format(node, visitor)
            self.fail(msg=message)
        message = 'Python node is not a {}'.format(py_node_type.__qualname__)
        self.assertIsInstance(py_node, py_node_type, msg=message)
        return py_node

    def _test_visitors(
        self,
        node: concat.parse.Node,
        visitors: Iterable[str],
        py_node_type: Type[ast.AST],
    ) -> Iterator[ast.AST]:
        for visitor in visitors:
            yield self._test_visitor(node, visitor, py_node_type)

    def _test_visitor_basic(
        self, node: concat.parse.Node, visitor: str
    ) -> ast.AST:
        return self._test_visitor(node, visitor, ast.Call)

    def test_funcdef_statement_visitor(self) -> None:
        """Function definitions are transpiled to the same kind of Python statement."""
        name_token = concat.lex.Token()
        name_token.value, name_token.start = 'a', (0, 0)
        empty = concat.parse.QuoteWordNode([], (0, 0), (0, 0))
        node = concat.parse.FuncdefStatementNode(
            name_token,
            [],
            [],
            [],
            [empty],
            (0, 0),
            StackEffectTypeNode(
                (0, 0),
                TypeSequenceNode((0, 0), (0, 0), None, []),
                TypeSequenceNode((0, 0), (0, 0), None, []),
            ),
        )

        self._test_visitors(
            node, {'funcdef-statement', 'statement'}, ast.FunctionDef
        )

    def test_import_statement_visitor_with_as(self) -> None:
        """import ... as ... statements are transpiled to the same kind of Python statement.

        The as-clause will be present in the resulting Python AST."""

        node = concat.parse.ImportStatementNode(
            'a.submodule', (0, 0), (0, 0), 'b'
        )

        for py_node in self._test_visitors(
            node, {'import-statement', 'statement'}, ast.stmt
        ):
            self.assertIn(
                'as b',
                astunparse.unparse(py_node),
                msg='as-part was not transpiled',
            )

    def test_import_statement_visitor_with_from(self) -> None:
        node = concat.parse.FromImportStatementNode(
            'a.submodule', 'b', (0, 0), (0, 0)
        )

        for py_node in self._test_visitors(
            node, {'import-statement', 'statement'}, ast.stmt
        ):
            self.assertIn(
                'from',
                astunparse.unparse(py_node),
                msg='was not transpiled as from-import',
            )

    def test_import_statement_visitor_with_from_and_as(self) -> None:
        node = concat.parse.FromImportStatementNode(
            'a.submodule', 'b', (0, 0), (0, 0), 'c'
        )

        for py_node in self._test_visitors(
            node, {'import-statement', 'statement'}, ast.stmt
        ):
            self.assertIn(
                'from',
                astunparse.unparse(py_node),
                msg='was not transpiled as from-import',
            )
            self.assertIn(
                'as c',
                astunparse.unparse(py_node),
                msg='as-part was not transpiled',
            )

    def test_import_statement_visitor_with_from_and_star(self) -> None:
        node = concat.parse.FromImportStarStatementNode('a', (0, 0), (0, 0))

        for py_node in self._test_visitors(
            node, {'import-statement', 'statement'}, ast.stmt
        ):
            self.assertIn(
                'from',
                astunparse.unparse(py_node),
                msg='was not transpiled as from-import',
            )
            self.assertIn(
                '*',
                astunparse.unparse(py_node),
                msg='star-part was not transpiled',
            )

    def test_classdef_statement_visitor(self) -> None:
        empty = concat.parse.QuoteWordNode([], (0, 0), (0, 0))
        node = concat.parse.ClassdefStatementNode('A', [empty], (0, 0), [])

        self._test_visitors(
            node, {'classdef-statement', 'statement'}, ast.ClassDef
        )

    def test_classdef_statement_visitor_with_decorators(self) -> None:
        name = Token()
        name.start, name.value = (0, 0), 'decorator'
        decorator = concat.parse.NameWordNode(name)
        node = concat.parse.ClassdefStatementNode(
            'A', [decorator], (0, 0), [decorator]
        )

        for py_node in self._test_visitors(
            node, {'classdef-statement', 'statement'}, ast.ClassDef
        ):
            self.assertIn(
                '@',
                astunparse.unparse(py_node),
                msg='decorator was not transpiled',
            )

    def test_classdef_statement_visitor_with_bases(self) -> None:
        name = Token()
        name.start, name.value = (0, 0), 'base'
        base = concat.parse.NameWordNode(name)
        node = concat.parse.ClassdefStatementNode(
            'A', [base], (0, 0), [], [[base]]
        )

        for py_node in self._test_visitors(
            node, {'classdef-statement', 'statement'}, ast.ClassDef
        ):
            self.assertIn(
                '(',
                astunparse.unparse(py_node),
                msg='bases were not transpiled',
            )
            self.assertIn(
                'base',
                astunparse.unparse(py_node),
                msg='bases were not transpiled',
            )

    def test_classdef_statement_visitor_with_keyword_args(self) -> None:
        name = Token()
        name.start, name.value = (0, 0), 'meta'
        word = concat.parse.NameWordNode(name)
        node = concat.parse.ClassdefStatementNode(
            'A', [word], (0, 0), [], [], [('metaclass', word)]
        )

        for py_node in self._test_visitors(
            node, {'classdef-statement', 'statement'}, ast.ClassDef
        ):
            self.assertIn(
                '(',
                astunparse.unparse(py_node),
                msg='keyword arguments were not transpiled',
            )
            self.assertIn(
                'metaclass=',
                astunparse.unparse(py_node),
                msg='keyword arguments were not transpiled',
            )
