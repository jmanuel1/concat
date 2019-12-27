"""Contains functionality to transpile Concat ASTs to Python ASTs.

We use the concept of visitor combinators, based on Visser (2001), to make
visitors easier to extend by composition. This is similar to the parser
combinator concept.

References:

Visser (2001): ACM SIGPLAN Notices 36(11):270-282 November 2001 DOI:
10.1145/504311.504302"""


import abc
import ast
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
    # Converts a TopLevelNode to the top level of a Python module
    @FunctionalVisitor
    def top_level_visitor(
        node: concat.level0.parse.TopLevelNode
    ) -> ast.Module:
        statement = visitors.ref_visitor('statement')
        word = visitors.ref_visitor('word')
        body = All(Choice(statement, word)).visit(node)
        module = ast.Module(body=body)
        ast.fix_missing_locations(module)
        return module

    visitors['top-level'] = top_level_visitor
