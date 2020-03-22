from typing import (
    TypeVar, Iterable, Generic, Callable, Tuple, Union, Dict, Type)
from typing_extensions import Protocol
import abc
import functools

NodeType1 = TypeVar('NodeType1')
NodeType1_co = TypeVar('NodeType1_co', covariant=True)
NodeType1_contra = TypeVar('NodeType1_contra', contravariant=True)
NodeType2 = TypeVar('NodeType2')
NodeType3 = TypeVar('NodeType3')
ReturnType1 = TypeVar('ReturnType1')
ReturnType1_co = TypeVar('ReturnType1_co', covariant=True)
ReturnType2 = TypeVar('ReturnType2')


class InternalNode(Protocol[NodeType1_co]):

    @property
    def children(self) -> Iterable[NodeType1_co]:
        ...


class VisitFailureException(Exception):
    pass


class Visitor(abc.ABC, Generic[NodeType1_contra, ReturnType1_co]):

    @abc.abstractmethod
    def visit(self, node: NodeType1_contra) -> ReturnType1_co:
        pass

    def then(self,
             other: 'Visitor[NodeType1_contra, ReturnType2]'
             ) -> 'Visitor[NodeType1_contra, ReturnType2]':
        @FunctionalVisitor
        def visitor(node: NodeType1_contra) -> ReturnType2:
            return Sequence(self, other).visit(node)[1]
        return visitor


class FunctionalVisitor(Visitor[NodeType1, ReturnType1]):
    """A decorator to create visitors from functions."""

    def __init__(self, func: Callable[[NodeType1], ReturnType1]):
        self.__func = func

    def visit(self, node: NodeType1) -> ReturnType1:
        return self.__func(node)

    def __repr__(self) -> str:
        type_name = type(self).__qualname__
        func_name = self.__func.__qualname__
        return '{}({})'.format(type_name, func_name)


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
        visitor2: Visitor[NodeType1, ReturnType2],
        debug: bool = False
    ):
        super().__init__()
        self.__visitor1, self.__visitor2 = visitor1, visitor2
        self.__debug = debug

    def visit(self, node: NodeType1) -> Union[ReturnType1, ReturnType2]:
        if self.__debug:
            print('in choice', repr(self),  '{')
        try:
            if self.__debug:
                print('trying', repr(self.__visitor1))
            result: Union[ReturnType1,
                          ReturnType2] = self.__visitor1.visit(node)
        except VisitFailureException:
            if self.__debug:
                print('trying', repr(self.__visitor2))
            result = self.__visitor2.visit(node)
        if self.__debug:
            print('} end choice')
        return result

    def __repr__(self) -> str:
        type_name = type(self).__qualname__
        visitor_reprs = repr(self.__visitor1), repr(self.__visitor2)
        return '{}({}, {})'.format(type_name, *visitor_reprs)


# Traversal combinators

class All(Visitor[InternalNode[NodeType1], Iterable[ReturnType1]]):
    """Visser's every-child traversal combinator."""

    def __init__(
        self, visitor: Visitor[NodeType1, ReturnType1], debug: bool = False
    ):
        super().__init__()
        self.__visitor = visitor
        self.__debug = debug

    def visit(self, node: InternalNode[NodeType1]) -> Iterable[ReturnType1]:
        if self.__debug:
            print('in', repr(self), ', visiting children of',
                  node, '(children:', node.children, ') {')
        # return a list instead of a generator so that the subvisitor actually
        # runs
        result = [self.__visitor.visit(child)
                  for child in node.children]
        if self.__debug:
            print('} end all')
        return result

    def __repr__(self) -> str:
        return '{}({})'.format(type(self).__qualname__, repr(self.__visitor))


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


# Useful visitors

def assert_type(type: Type[object]):
    @FunctionalVisitor
    def visitor(node: object) -> None:
        if not isinstance(node, type):
            raise VisitFailureException
    return visitor


T = TypeVar('T')


class VisitorDict(Dict[str, Visitor[NodeType1, ReturnType1]]):

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.data: Dict = {}

    def extend_with(self: T, extension: Callable[[T], None]) -> None:
        extension(self)

    def visit(self, node: NodeType1) -> ReturnType1:
        return self['top-level'].visit(node)

    def ref_visitor(self, name: str) -> Visitor[NodeType1, ReturnType1]:
        @FunctionalVisitor
        def visit(node: NodeType1) -> ReturnType1:
            return self[name].visit(node)

        return visit
