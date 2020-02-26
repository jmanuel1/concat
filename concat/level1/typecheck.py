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
        if isinstance(other, GenericArityTypedStackEffect):
            if not isinstance(self, GenericArityTypedStackEffect):
                self = GenericArityTypedStackEffect(
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
        return functools.reduce(cls.compose, effects, cls._noop_type())

    @classmethod
    def _noop_type(cls) -> 'StackEffect':
        return cls(0, 0)


_Type = Union[str, 'GenericArityTypedStackEffect.Variable', 'StackEffect']


@dataclasses.dataclass
class GenericArityTypedStackEffect(StackEffect):
    class Variable:
        pass
    _in_types: Sequence[_Type]
    _out_types: Sequence[_Type]

    def __init__(self, in_types: Sequence[_Type], out_types: Sequence[_Type]):
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

    def compose(self, other: StackEffect) -> 'GenericArityTypedStackEffect':
        if not isinstance(other, GenericArityTypedStackEffect):
            other = GenericArityTypedStackEffect(
                ['object'] * other.in_arity, ['object'] * other.out_arity)
        # unify self out types and other in types
        unifications = self.__unify(self._out_types, other._in_types)
        self = self.__bind(unifications)
        other = other.__bind(unifications)
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
        result = type(self)(in_types, out_types)
        print(self, other, result)
        return result

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

    @classmethod
    def _noop_type(cls) -> 'GenericArityTypedStackEffect':
        return cls((), ())

    def __str__(self) -> str:
        return '({} -- {})'.format(' '.join(str(type) for type in self._in_types), ' '.join(str(type) for type in self._out_types))

    @classmethod
    def __unify(cls, type_list: Sequence[_Type], other_type_list: Sequence[_Type]) -> Dict[Variable, Sequence[_Type]]:
        unifications = {}
        i, j = len(type_list) - 1, len(other_type_list) - 1
        while i > -1 and j > -1:
            type1, type2 = type_list[i], other_type_list[j]
            if isinstance(type1, cls.Variable):
                if i == 0:
                    unifications[type1] = other_type_list[:j + 1]
                    j = -1
                else:
                    next_type = type_list[i - 1]
                    next_type_index = _rindex(
                        other_type_list, next_type, j)
                    unifications[type1] = other_type_list[next_type_index + 1: j + 1]
                    j = next_type_index
                i -= 1
            elif isinstance(type2, cls.Variable):
                raise NotImplementedError
            elif isinstance(type1, GenericArityTypedStackEffect) and isinstance(type2, GenericArityTypedStackEffect):
                type1 = type1.__bind(unifications)
                type2 = type2.__bind(unifications)
                unifs = cls.__unify(type1._in_types, type2._in_types)
                type1 = type1.__bind(unifs)
                type2 = type2.__bind(unifs)
                unifs.update(cls.__unify(type1._out_types, type2._out_types))
                type1 = type1.__bind(unifs)
                type2 = type2.__bind(unifs)
                if type1 != type2:
                    print('tried unifying', type1, 'with', type2)
                    print('first:', type_list, 'other:', other_type_list)
                    raise TypeError('{} does not unify with {}'.format(
                        type_list, other_type_list))
                unifications.update(unifs)
            elif isinstance(type2, StackEffect):
                raise NotImplementedError
            else:
                if type1 != type2:
                    print('tried unifying', type1, 'with', type2)
                    print('first:', type_list, 'other:', other_type_list)
                    raise TypeError('{} does not unify with {}'.format(
                        type_list, other_type_list))
                i -= 1
                j -= 1
        return unifications

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
    return GenericArityTypedStackEffect(in_types, out_types)


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
    GenericArityTypedStackEffect.compose_all(
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
    in_var = GenericArityTypedStackEffect.Variable()
    out_var = GenericArityTypedStackEffect.Variable()
    return GenericArityTypedStackEffect((in_var, 'iterable', GenericArityTypedStackEffect((in_var,), (out_var,))), (out_var,))


@concat.level0.transpile.FunctionalVisitor
def _invert_word_check(closure: _Closure) -> StackEffect:
    _assert_tree_type(concat.level1.parse.InvertWordNode).visit(closure)
    # FIXME: Though this usually pushes an int, __invert__ could return anything when called on anything
    return GenericArityTypedStackEffect(('int',), ('int',))


_operator_word_check = concat.level0.transpile.alt(_invert_word_check)


@concat.level0.transpile.FunctionalVisitor
def _num_word_check(closure: _Closure) -> StackEffect:
    _assert_tree_type(concat.level0.parse.NumberWordNode).visit(closure)
    if isinstance(closure.tree.value, int):
        return GenericArityTypedStackEffect((), ('int',))
    raise NotImplementedError('other numeric literal types')


@concat.level0.transpile.FunctionalVisitor
def _dict_word_check(closure: _Closure) -> StackEffect:
    _assert_tree_type(concat.level1.parse.DictWordNode).visit(closure)
    return GenericArityTypedStackEffect((), ('dict',))


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
