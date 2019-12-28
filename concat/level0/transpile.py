"""Contains functionality to transpile Concat ASTs to Python ASTs.

We use the concept of visitor combinators, based on Visser (2001), to make
visitors easier to extend by composition. This is similar to the parser
combinator concept.

References:

Visser (2001): ACM SIGPLAN Notices 36(11):270-282 November 2001 DOI:
10.1145/504311.504302"""


import abc
import ast
import functools
# import astunparse # TODO: install astunparse
from typing import Tuple, Union, TypeVar, Generic, Iterable, Dict, Callable
from typing_extensions import Protocol
import concat.level0.parse


NodeType1 = TypeVar('NodeType1')
NodeType1_contra = TypeVar('NodeType1_contra', contravariant=True)
NodeType2 = TypeVar('NodeType2')
NodeType3 = TypeVar('NodeType3')
ReturnType1 = TypeVar('ReturnType1')
ReturnType1_co = TypeVar('ReturnType1_co', covariant=True)
ReturnType2 = TypeVar('ReturnType2')


class InternalNode(Protocol[NodeType1]):

    children: Iterable[NodeType1]


class VisitFailureException(Exception):
    pass


class Visitor(abc.ABC, Generic[NodeType1_contra, ReturnType1_co]):

    @abc.abstractmethod
    def visit(self, node: NodeType1_contra) -> ReturnType1_co:
        pass


class FunctionalVisitor(Visitor[NodeType1, ReturnType1]):
    """A decorator to create visitors from functions."""

    def __init__(self, func: Callable[[NodeType1], ReturnType1]):
        self.__func = func

    def visit(self, node: NodeType1) -> ReturnType1:
        return self.__func(node)


class Identity(Visitor[NodeType1, NodeType1]):
    """Visser's do-nothing visitor."""

    def visit(self, node: NodeType1) -> NodeType1:
        return node


class Sequence(Visitor[NodeType1, Tuple[ReturnType1, ReturnType2]]):
    """Visser's sequential visitor combinator (like and)."""

    def __init__(
        self,
        visitor1: Visitor[NodeType1, ReturnType1],
        visitor2: Visitor[NodeType1, ReturnType2]
    ):
        super().__init__()
        self.__visitor1, self.__visitor2 = visitor1, visitor2

    def visit(self, node: NodeType1) -> Tuple[ReturnType1, ReturnType2]:
        return self.__visitor1.visit(node), self.__visitor2.visit(node)


class Choice(Visitor[NodeType1, Union[ReturnType1, ReturnType2]]):
    """Visser's one-or-the-other combinator (like or).

    This is 'left-biased': the first visitor is tried first, and its result is
    returned without trying the second visitor if the first succeeds."""

    def __init__(
        self,
        visitor1: Visitor[NodeType1, ReturnType1],
        visitor2: Visitor[NodeType1, ReturnType2]
    ):
        super().__init__()
        self.__visitor1, self.__visitor2 = visitor1, visitor2

    def visit(self, node: NodeType1) -> Union[ReturnType1, ReturnType2]:
        try:
            return self.__visitor1.visit(node)
        except VisitFailureException:
            return self.__visitor2.visit(node)


# Traversal combinators

class All(Visitor[InternalNode[NodeType1], Iterable[ReturnType1]]):
    """Visser's every-child traversal combinator."""

    def __init__(self, visitor: Visitor[NodeType1, ReturnType1]):
        super().__init__()
        self.__visitor = visitor

    def visit(self, node: InternalNode[NodeType1]) -> Iterable[ReturnType1]:
        return (self.__visitor.visit(child) for child in node.children)


class One(Visitor[InternalNode[NodeType1], ReturnType1]):
    """Visser's combinator that tries visiting each child until success."""

    def __init__(self, visitor: Visitor[NodeType1, ReturnType1]):
        super().__init__()
        self.__visitor = visitor

    def visit(self, node: InternalNode[NodeType1]) -> ReturnType1:
        for child in node.children:
            try:
                return self.__visitor.visit(child)
            except VisitFailureException:
                continue
        raise VisitFailureException


# Beyond Visser's combinators

def alt(*visitors):
    return functools.reduce(Choice, visitors)


T = TypeVar('T')


class VisitorDict(Dict[str, Visitor[NodeType1, ReturnType1]]):

    def extend_with(self: T, extension: Callable[[T], None]) -> None:
        extension(self)

    def visit(self, node: NodeType1) -> ReturnType1:
        return self['top-level'].visit(node)

    def ref_visitor(self, name: str) -> Visitor[NodeType1, ReturnType1]:
        @FunctionalVisitor
        def visit(node: NodeType1) -> ReturnType1:
            return self[name].visit(node)

        return visit


def level_0_extension(
    visitors: VisitorDict[concat.level0.parse.Node, ast.AST]
) -> None:
    def statementfy(node):
        if isinstance(node, ast.expr):
            return ast.Expr(value=node)
        return node

    # Converts a TopLevelNode to the top level of a Python module
    @FunctionalVisitor
    def top_level_visitor(
        node: concat.level0.parse.TopLevelNode
    ) -> ast.Module:
        statement = visitors.ref_visitor('statement')
        word = visitors.ref_visitor('word')
        body = list(All(Choice(statement, word)).visit(node))
        statements = [statementfy(child) for child in body]
        module = ast.Module(body=statements)
        ast.fix_missing_locations(module)
        # debugging output
        # with open('debug.py', 'w') as f:
        #     f.write(astunparse.unparse(module))
        with open('ast.out', 'w') as f:
            f.write('------------ AST DUMP ------------\n')
            # f.write(astunparse.dump(module))
            f.write(ast.dump(module))
        return module

    visitors['top-level'] = top_level_visitor

    visitors['statement'] = visitors.ref_visitor('import-statement')

    # Converts an ImportStatementNode to a Python import statement node
    @FunctionalVisitor
    def import_statement_visitor(node: concat.level0.parse.Node) -> ast.Import:
        if not isinstance(node, concat.level0.parse.ImportStatementNode):
            raise VisitFailureException
        import_node = ast.Import([ast.alias(node.value, None)])
        import_node.lineno, import_node.col_offset = node.location
        return import_node

    visitors['import-statement'] = import_statement_visitor

    visitors['word'] = alt(
        visitors.ref_visitor('push-word'),
        visitors.ref_visitor('quote-word'),
        visitors.ref_visitor('literal-word'),
        visitors.ref_visitor('name-word'),
        visitors.ref_visitor('attribute-word')
    )

    # Converts a QuoteWordNode to a Python expression which is a sequence.
    @FunctionalVisitor
    def quote_word_visitor(node: concat.level0.parse.Node):
        if not isinstance(node, concat.level0.parse.QuoteWordNode):
            raise VisitFailureException
        children = All(visitors.ref_visitor('word')).visit(node)
        py_node = ast.List(elts=children, ctx=ast.Load())
        py_node.lineno, py_node.col_offset = node.location
        return py_node

    visitors['quote-word'] = quote_word_visitor

    # Converts a PushWordNode to a Python call to stack.append
    @FunctionalVisitor
    def push_word_visitor(node: concat.level0.parse.Node) -> ast.Call:
        if not isinstance(node, concat.level0.parse.PushWordNode):
            raise VisitFailureException
        child = visitors.ref_visitor('word').visit(node.children[0])
        load = ast.Load()
        stack = ast.Name(id='stack', ctx=load)
        append_method = ast.Attribute(value=stack, attr='append', ctx=load)
        py_node = ast.Call(func=append_method, expr=[child], keywords=[])
        py_node.lineno, py_node.col_offset = node.location
        return py_node

    visitors['push-word'] = push_word_visitor

    visitors['literal-word'] = Choice(
        visitors.ref_visitor('number-word'),
        visitors.ref_visitor('string-word')
    )

    # Converts a NumberWordNode to a ast.Num
    @FunctionalVisitor
    def number_word_visitor(node: concat.level0.parse.Node) -> ast.Num:
        if not isinstance(node, concat.level0.parse.NumberWordNode):
            raise VisitFailureException
        py_node = ast.Num(n=node.value)
        py_node.lineno, py_node.col_offset = node.location
        return py_node

    visitors['number-word'] = number_word_visitor

    # Converts a StringWordNode to a ast.Str
    @FunctionalVisitor
    def string_word_visitor(node: concat.level0.parse.Node) -> ast.Str:
        if not isinstance(node, concat.level0.parse.StringWordNode):
            raise VisitFailureException
        py_node = ast.Str(s=node.value)
        py_node.lineno, py_node.col_offset = node.location
        return py_node

    visitors['string-word'] = string_word_visitor

    # Converts a AttributeWordNode to be an attribute lookup on the top of the stack
    @FunctionalVisitor
    def attribute_word_visitor(node: concat.level0.parse.Node):
        if not isinstance(node, concat.level0.parse.AttributeWordNode):
            raise VisitFailureException
        load = ast.Load()
        stack = ast.Name(id='stack', ctx=load)
        negative_one = ast.Num(n=-1)
        negative_one_index = ast.Index(value=negative_one)
        top = ast.Subscript(value=stack, slice=negative_one_index, ctx=load)
        attribute = ast.Attribute(value=top, attr=node.value, ctx=load)
        attribute.lineno, attribute.col_offset = node.location
        return attribute

    visitors['attribute-word'] = attribute_word_visitor
