"""The Concat type checker."""
import dataclasses
import builtins
import functools
from typing import List, Iterable, Dict, Type, Sequence, Optional, TypeVar, Generic, Union, Mapping
import concat.level0.lex
import concat.level0.parse
import concat.level0.transpile
import concat.level1.parse
import concat.level1.transpile
import parsy


class TypeError(builtins.TypeError):
    pass


@dataclasses.dataclass
class StackEffect:
    """Holds the input and output arity of a word."""
    in_arity: int
    out_arity: int

    def compose(self, other: 'StackEffect') -> 'StackEffect':
        if isinstance(other, TypedStackEffect):
            if not isinstance(self, TypedStackEffect):
                self = TypedStackEffect(
                    ['object'] * self.in_arity, ['object'] * self.out_arity)
            return self.compose(other)
        self_stack_underflow = -self.in_arity
        composed_stack_underflow = self_stack_underflow + \
            self.out_arity - other.in_arity
        stack_underflow = min(self_stack_underflow, composed_stack_underflow)
        in_arity = -stack_underflow
        out_arity = composed_stack_underflow + other.out_arity - stack_underflow
        result = StackEffect(in_arity, out_arity)
        print(self, other, result)
        return result

    def can_be_complete_program(self) -> bool:
        return self.in_arity == 0

    @classmethod
    def compose_all(cls, effects: Iterable['StackEffect']) -> 'StackEffect':
        return functools.reduce(cls.compose, effects, cls.noop_type())

    @classmethod
    def noop_type(cls) -> 'StackEffect':
        return cls(0, 0)


@dataclasses.dataclass
class TypedStackEffect(StackEffect):
    """Holds the types expected by and outputted by a word, along with arities."""
    _in_types: Sequence[str]
    _out_types: Sequence[str]

    def __init__(self, in_types: Sequence[str], out_types: Sequence[str]) -> None:
        super().__init__(len(in_types), len(out_types))
        self._in_types, self._out_types = in_types, out_types

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, StackEffect):
            return NotImplemented
        # We create an object of the supertype because default dataclass __eq__
        # returns NotImplemented when the types of the arguments are not
        # identical
        if not StackEffect(len(self._in_types), len(self._out_types)).__eq__(other):
            print('HERE')
            return False
        if isinstance(other, type(self)):
            # We make sure that all the in/out type sequences are tuples
            return (*self._in_types,) == (*other._in_types,) and \
                (*self._out_types,) == (*other._out_types,)
        return True

    def compose(self, other: StackEffect) -> 'TypedStackEffect':
        if not isinstance(other, type(self)):
            other = type(self)(['object'] * other.in_arity,
                               ['object'] * other.out_arity)
        # FIXME: this function should not be aware of its subclass versions
        if isinstance(other, GenericArityTypedStackEffect):
            return GenericArityTypedStackEffect(self._in_types, self._out_types).compose(other)
        # type checking
        for out_type, in_type in zip(reversed(self._out_types), reversed(other._in_types)):
            if in_type != out_type:
                print('tried to compose', self, 'and', other)
                raise TypeError("{!r} does not match {!r}".format(
                    self._out_types, other._in_types))
        self_stack_underflow = -self.in_arity
        composed_stack_underflow = self_stack_underflow + \
            self.out_arity - other.in_arity
        stack_underflow = min(self_stack_underflow, composed_stack_underflow)
        if stack_underflow == self_stack_underflow:
            in_types = self._in_types
        else:
            in_types = [
                *other._in_types[-(-composed_stack_underflow - other.in_arity):], *self._in_types]
        out_arity = composed_stack_underflow + other.out_arity - stack_underflow
        out_types = [
            *self._out_types[-(out_arity - len(other._out_types)) + 1:], *other._out_types]
        result = TypedStackEffect(in_types, out_types)
        print(self, other, result)
        return result

    @classmethod
    def noop_type(cls) -> 'TypedStackEffect':
        return cls((), ())


_Type = Union[str, 'GenericArityTypedStackEffect.Variable', 'StackEffect']


@dataclasses.dataclass
class GenericArityTypedStackEffect(TypedStackEffect):
    class Variable:
        pass
    _in_types: Sequence[_Type]  # type: ignore
    _out_types: Sequence[_Type]  # type: ignore

    def __init__(self, in_types: Sequence[_Type], out_types: Sequence[_Type]):
        super().__init__(in_types, out_types)  # type: ignore

    def compose(self, other: StackEffect) -> 'GenericArityTypedStackEffect':
        if not isinstance(other, GenericArityTypedStackEffect):
            if isinstance(other, TypedStackEffect):
                other = GenericArityTypedStackEffect(
                    other._in_types, other._out_types)
            else:
                other = GenericArityTypedStackEffect(
                    ['object'] * other.in_arity, ['object'] * other.out_arity)
        # unify self out types and other in types
        i, j = len(self._out_types) - 1, len(other._in_types) - 1
        unifications = {}
        while i > -1 and j > -1:
            type1, type2 = self._out_types[i], other._in_types[j]
            if isinstance(type1, self.Variable):
                if i == 0:
                    unifications[type1] = other._in_types[:j + 1]
                else:
                    next_type = self._out_types[i - 1]
                    next_type_index = _rindex(
                        other._in_types, next_type, j)
                    unifications[type1] = other._in_types[next_type_index + 1: j + 1]
            elif isinstance(type2, self.Variable):
                raise NotImplementedError
            else:
                if type1 != type2:
                    raise TypeError('{!r} does not unify with {!r}'.format(
                        self._out_types, other._in_types))
        # this is wrong
        # type: ignore
        return super(type(self), self.__bind(unifications)).compose(other.__bind(unifications))

    def __repr__(self) -> str:
        return super().__repr__()

    def __bind(self, unifications: Mapping[Variable, Sequence[_Type]]) -> 'GenericArityTypedStackEffect':
        in_types: List[_Type] = []
        for type in self._in_types:
            if isinstance(type, self.Variable):
                in_types += unifications.get(type, [type])
            elif isinstance(type, GenericArityTypedStackEffect):
                in_types.append(type.__bind(unifications))
            else:
                in_types.append(type)
        out_types: List[_Type] = []
        for type in self._out_types:
            if isinstance(type, self.Variable):
                out_types += unifications.get(type, [type])
            elif isinstance(type, GenericArityTypedStackEffect):
                out_types.append(type.__bind(unifications))
            else:
                out_types.append(type)
        return GenericArityTypedStackEffect(in_types, out_types)


_T = TypeVar('_T', bound=concat.level0.parse.Node)
_U = TypeVar('_U', bound=concat.level0.parse.Node)
_V = TypeVar('_V')


@dataclasses.dataclass
class _Closure(Generic[_T]):
    """A closure is an AST and a dictionary of names of free variables to types."""
    tree: _T
    environment: Dict[str, StackEffect]

    @property
    def children(self) -> List['_Closure[_U]']:
        return [_Closure(child, self.environment) for child in self.tree.children]


def _rindex(seq: Sequence[_V], elem: _V, last_index: int) -> int:
    for i in range(last_index, -1, -1):
        e = seq[i]
        if e == elem:
            return i
    raise ValueError('not found')


def _ensure_type(name: Optional[concat.level0.lex.Token]) -> str:
    if name is None:
        return 'object'
    return name.value


def parse_stack_effect(tokens: List[concat.level0.lex.Token]) -> StackEffect:
    parser_dict = concat.level0.parse.ParserDict()
    item = parsy.seq(parser_dict.token('NAME'), (parser_dict.token(
        'COLON') >> parser_dict.token('NAME')).optional())
    separator = parser_dict.token('MINUS').times(2)
    items = item.many()
    stack_effect = parsy.seq(items << separator, items)
    parsed_effect = stack_effect.parse(tokens)
    in_types = [_ensure_type(item[1]) for item in parsed_effect[0]]
    out_types = [_ensure_type(item[1]) for item in parsed_effect[1]]
    return TypedStackEffect(in_types, out_types)


def check(tree: concat.level0.parse.TopLevelNode, env: Dict[str, StackEffect] = {}) -> None:
    _top_level_check.visit(_Closure(tree, env))


def _assert_tree_type(
    cls: Type[concat.level0.parse.Node]
) -> concat.level0.transpile.Visitor[_Closure, None]:
    @concat.level0.transpile.FunctionalVisitor
    def visitor(closure: _Closure) -> None:
        concat.level1.transpile.assert_type(cls).visit(closure.tree)
    return visitor


@concat.level0.transpile.FunctionalVisitor
def __top_level_check(closure: _Closure[concat.level0.parse.TopLevelNode]) -> None:
    effects = concat.level0.transpile.All(concat.level0.transpile.Choice(
        _statement_check, _word_check)).visit(closure)
    TypedStackEffect.compose_all(
        [effect for effect in effects if effect is not None])


_top_level_check = _assert_tree_type(
    concat.level0.parse.TopLevelNode).then(__top_level_check)


@concat.level0.transpile.FunctionalVisitor
def _quote_word_check(closure: _Closure) -> StackEffect:
    _assert_tree_type(concat.level0.parse.QuoteWordNode).visit(closure)
    if isinstance(closure.tree, concat.level1.parse.TryWordNode):
        print('HERE _quote_word_check')
    effects = concat.level0.transpile.All(_word_check).visit(closure)
    return StackEffect.compose_all(effects)


@concat.level0.transpile.FunctionalVisitor
def _push_word_check(closure: _Closure) -> StackEffect:
    effects = _assert_tree_type(
        concat.level0.parse.PushWordNode).then(concat.level0.transpile.All(_word_check)).visit(closure)
    return GenericArityTypedStackEffect((), (GenericArityTypedStackEffect.compose_all(effects),))


@concat.level0.transpile.FunctionalVisitor
def __name_word_check(closure: _Closure[concat.level0.parse.NameWordNode]) -> StackEffect:
    return closure.environment[closure.tree.value]


_name_word_check = _assert_tree_type(
    concat.level0.parse.NameWordNode).then(__name_word_check)


@concat.level0.transpile.FunctionalVisitor
def _with_word_check(closure: _Closure) -> StackEffect:
    _assert_tree_type(concat.level1.parse.WithWordNode).visit(closure)
    in_var = GenericArityTypedStackEffect.Variable()
    out_var = GenericArityTypedStackEffect.Variable()
    return GenericArityTypedStackEffect((in_var, GenericArityTypedStackEffect((in_var, 'object'), (out_var,)), 'context_manager'), (out_var,))


@concat.level0.transpile.FunctionalVisitor
def _try_word_check(closure: _Closure) -> StackEffect:
    _assert_tree_type(concat.level1.parse.TryWordNode).visit(closure)
    # FIXME: This should depend on the function argument's stack effect
    return StackEffect(2, 0)


@concat.level0.transpile.FunctionalVisitor
def _invert_word_check(closure: _Closure) -> StackEffect:
    _assert_tree_type(concat.level1.parse.InvertWordNode).visit(closure)
    # FIXME: Though this usually pushes an int, __invert__ could return anything when called on anything
    return TypedStackEffect(('int',), ('int',))


_operator_word_check = concat.level0.transpile.alt(_invert_word_check)


@concat.level0.transpile.FunctionalVisitor
def _num_word_check(closure: _Closure) -> StackEffect:
    _assert_tree_type(concat.level0.parse.NumberWordNode).visit(closure)
    if isinstance(closure.tree.value, int):
        return TypedStackEffect((), ('int',))
    raise NotImplementedError('other numeric literal types')


@concat.level0.transpile.FunctionalVisitor
def _dict_word_check(closure: _Closure) -> StackEffect:
    _assert_tree_type(concat.level1.parse.DictWordNode).visit(closure)
    return TypedStackEffect((), ('dict',))


_literal_word_check = concat.level0.transpile.alt(
    _num_word_check, _dict_word_check)

_word_check = concat.level0.transpile.alt(
    _quote_word_check, _push_word_check, _name_word_check, _with_word_check,
    _try_word_check, _literal_word_check, _operator_word_check)


@concat.level0.transpile.FunctionalVisitor
def _funcdef_statement_check(closure: _Closure) -> None:
    _assert_tree_type(concat.level1.parse.FuncdefStatementNode).visit(closure)
    tree = closure.tree
    explicit_effect = tree.stack_effect
    body_effects = (_word_check.visit(_Closure(word, closure.environment))
                    for word in tree.body if isinstance(word, concat.level0.parse.WordNode))
    implicit_effect = StackEffect.compose_all(body_effects)
    if explicit_effect is not None and explicit_effect != implicit_effect:
        raise TypeError


_statement_check = concat.level0.transpile.alt(_funcdef_statement_check)
