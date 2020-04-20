"""The Concat type checker.

The type inference algorithm is based on the one described in "Robert Kleffner:
A Foundation for Typed Concatenative Languages, April 2017."
"""

import abc
import dataclasses
import builtins
from typing import (List, Set, Tuple, Dict, Iterator, Union,
                    Optional, Generator, Callable, overload, cast)
import concat.astutils
import concat.parser_combinators
import concat.level0.parse
import concat.level1.parse
import parsy


class TypeError(builtins.TypeError):
    pass


class NameError(builtins.NameError):
    def __init__(self, name: concat.level0.parse.NameWordNode):
        super().__init__(name)
        self._name = name
        self.location = name.location

    def __str__(self):
        return 'name "{}" not previously defined (error at {}:{})'.format(
            self._name.value, *self.location)


class Type(abc.ABC):
    def to_for_all(self) -> 'ForAll':
        return ForAll([], self)

    def is_subtype_of(self, supertype: 'Type') -> bool:
        if supertype is self or supertype is PrimitiveTypes.object:
            return True
        if isinstance(supertype, IndividualVariable):
            return self.is_subtype_of(supertype.bound)
        return False

    def __and__(self, other: object) -> '_IntersectionType':
        if not isinstance(other, Type):
            return NotImplemented
        return _IntersectionType(self, other)


@dataclasses.dataclass
class _IntersectionType(Type):
    type_1: Type
    type_2: Type

    def __repr__(self) -> str:
        return '{} & {}'.format(self.type_1, self.type_2)

    def is_subtype_of(self, other: Type) -> bool:
        return (super().is_subtype_of(other)
                or self.type_1.is_subtype_of(other)
                or self.type_2.is_subtype_of(other))


@dataclasses.dataclass
class PrimitiveInterface(Type):
    _name: str = '<primitive_interface>'


class PrimitiveInterfaces:
    invertible = PrimitiveInterface('invertible')


@dataclasses.dataclass
class _BuiltinType(Type):
    _name: str = '<primitive_type>'
    _supertypes: Tuple[Type, ...] = dataclasses.field(default_factory=tuple)

    def is_subtype_of(self, supertype: Type) -> bool:
        return super().is_subtype_of(
            supertype) or supertype in self._supertypes

    def add_supertype(self, supertype: Type) -> None:
        self._supertypes += (supertype,)


class PrimitiveTypes:
    int = _BuiltinType('int', (PrimitiveInterfaces.invertible,))
    bool = _BuiltinType('bool')
    object = _BuiltinType('object')
    context_manager = _BuiltinType('context_manager')
    iterable = _BuiltinType('iterable')
    dict = _BuiltinType('dict', (iterable,))
    file = _BuiltinType('file')
    str = _BuiltinType('str')
    module = _BuiltinType('module')
    list = _BuiltinType('list', (iterable,))
    py_function = _BuiltinType('py_function')


class _Variable(Type, abc.ABC):
    """Objects that represent type variables.

    Every type variable object is assumed to be unique. Thus, fresh type
    variables can be made simply by creating new objects. They can also be
    compared by identity."""
    pass


class SequenceVariable(_Variable):
    pass


@dataclasses.dataclass
class IndividualVariable(_Variable):
    bound: Type = PrimitiveTypes.object

    def is_subtype_of(self, supertype: Type):
        return super().is_subtype_of(supertype) or self.bound.is_subtype_of(
            supertype)

    def __hash__(self) -> int:
        return hash(id(self))


@dataclasses.dataclass
class ForAll(Type):
    quantified_variables: List[_Variable]
    type: Type

    def to_for_all(self) -> 'ForAll':
        return self


@dataclasses.dataclass
class _Function(Type):
    input: List[Type]
    output: List[Type]

    def __iter__(self) -> Iterator[List[Type]]:
        return iter((self.input, self.output))

    def generalized_wrt(self, gamma: Dict[str, Type]) -> ForAll:
        return ForAll(list(_ftv(self) - _ftv(gamma)), self)

    def can_be_complete_program(self) -> bool:
        """Returns true iff the function type unifies with ( -- *out)."""
        out_var = SequenceVariable()
        try:
            unify_ind(self, _Function([], [out_var]))
        except TypeError:
            return False
        return True

    def compose(self, other: '_Function') -> '_Function':
        """Returns the type of applying self then other to a stack."""
        i2, o2 = other
        (i1, o1) = self
        phi = unify(o1, i2)
        return phi(_Function(i1, o2))

    def __eq__(self, other: object) -> bool:
        """Compares function types for equality up to renaming of variables."""
        if not isinstance(other, _Function):
            return NotImplemented
        input_arity_matches = len(self.input) == len(other.input)
        output_arity_matches = len(self.output) == len(other.output)
        arities_match = input_arity_matches and output_arity_matches
        if not arities_match:
            return False
        # We can't use plain unification here because variables can only map to
        # variables of the same type.
        subs = Substitutions()
        type_pairs = zip(self.input + self.output, other.input + other.output)
        for type1, type2 in type_pairs:
            if isinstance(type1, IndividualVariable) and \
                    isinstance(type2, IndividualVariable):
                subs[type2] = type1
            elif isinstance(type1, SequenceVariable) and \
                    isinstance(type2, SequenceVariable):
                subs[type2] = type1
            type2 = subs(type2)
            if type1 != type2:
                return False
        return True

    def is_subtype_of(self, supertype: Type) -> bool:
        if super().is_subtype_of(supertype):
            return True
        if isinstance(supertype, _Function):
            if (len(self.input) != len(supertype.input)
                    or len(self.output) != len(supertype.output)):
                return False
            # input types are contravariant
            for type_from_self, type_from_supertype in zip(
                    self.input, supertype.input):
                if not type_from_supertype.is_subtype_of(type_from_self):
                    return False
            # output types are covariant
            for type_from_self, type_from_supertype in zip(
                    self.output, supertype.output):
                if not type_from_self.is_subtype_of(type_from_supertype):
                    return False
            return True
        return False


@dataclasses.dataclass
class TypeWithAttribute(Type):
    attribute: str
    attribute_type: Type

    def is_subtype_of(self, supertype: Type) -> bool:
        if super().is_subtype_of(supertype):
            return True
        elif isinstance(supertype, TypeWithAttribute):
            return (self.attribute == supertype.attribute
                    and self.attribute_type.is_subtype_of(
                        supertype.attribute_type))
        raise NotImplementedError(supertype)


# expose _Function as StackEffect
StackEffect = _Function


class Environment(Dict[str, Type]):
    pass


class Substitutions(Dict[_Variable, Union[Type, List[Type]]]):

    _T = Union['Substitutions', Type, List[Type], Environment]

    @overload
    def __call__(self, arg: 'Substitutions') -> 'Substitutions':
        ...

    @overload
    def __call__(self, arg: _BuiltinType) -> _BuiltinType:
        ...

    @overload
    def __call__(self, arg: _Function) -> _Function:
        ...

    @overload
    def __call__(self, arg: ForAll) -> ForAll:
        ...

    @overload
    def __call__(self, arg: IndividualVariable) -> Type:
        ...

    @overload
    def __call__(
        self,
        arg: SequenceVariable
    ) -> Union[SequenceVariable, List[Type]]:
        ...

    @overload
    def __call__(self, arg: Type) -> Type:
        ...

    @overload
    def __call__(self, arg: List[Type]) -> List[Type]:
        ...

    @overload
    def __call__(self, arg: Environment) -> Environment:
        ...

    def __call__(self, arg: '_T') -> '_T':
        if isinstance(arg, Substitutions):
            return Substitutions({
                **self,
                **{a: self(i) for a, i in arg.items() if a not in self._dom()}
            })
        elif isinstance(arg, _BuiltinType):
            return arg
        elif isinstance(arg, _Function):
            return _Function(self(arg.input), self(arg.output))
        elif isinstance(arg, ForAll):
            return ForAll(
                arg.quantified_variables,
                Substitutions({
                    a: i
                    for a, i in self.items()
                    if a not in arg.quantified_variables
                })(arg.type)
            )
        elif isinstance(arg, _Variable) and arg in self:
            return self[arg]
        elif isinstance(arg, list):
            subbed_types = []
            for type in arg:
                subbed_type = self(type)
                if isinstance(subbed_type, list):
                    subbed_types += subbed_type
                else:
                    subbed_types.append(subbed_type)
            return subbed_types
        elif isinstance(arg, Environment):
            return Environment({name: self(t) for name, t in arg.items()})
        else:
            return arg

    def _dom(self) -> Set[_Variable]:
        return {*self}


_InferFunction = Callable[
    [Environment, 'concat.astutils.WordsOrStatements'],
    Tuple[Substitutions, _Function]
]


def _inst(sigma: ForAll) -> Type:
    """This is the inst function described by Kleffner."""
    subs = Substitutions({a: type(a)() for a in sigma.quantified_variables})
    return subs(sigma.type)


def infer(
    gamma: Environment,
    e: 'concat.astutils.WordsOrStatements',
    extensions: Optional[Tuple[_InferFunction]] = None
) -> Tuple[Substitutions, _Function]:
    """The infer function described by Kleffner."""
    e = list(e)
    # HACK: For now this works, but I might want a better way to pass around
    # the extensions later
    infer._extensions = (   # type: ignore
        infer._extensions  # type: ignore
        if extensions is None else extensions)
    if len(e) == 0:
        a_bar = SequenceVariable()
        return Substitutions(), _Function([a_bar], [a_bar])
    elif isinstance(e[-1], concat.level0.parse.NumberWordNode):
        S, i_to_o = infer(gamma, e[:-1])
        if isinstance(e[-1].value, int):
            i_to_o.output.append(PrimitiveTypes.int)
            return S, i_to_o
        else:
            raise NotImplementedError
    # there's no False word at the moment
    elif isinstance(e[-1], concat.level1.parse.TrueWordNode):
        S, i_to_o = infer(gamma, e[:-1])
        i_to_o.output.append(PrimitiveTypes.bool)
        return S, i_to_o
    elif isinstance(e[-1], concat.level1.parse.AddWordNode):
        # for now, only works with ints
        S, (i, o) = infer(gamma, e[:-1])
        a_bar = SequenceVariable()
        phi = unify(o, [
            a_bar, PrimitiveTypes.int, PrimitiveTypes.int])
        return phi(S), phi(_Function(i, [a_bar, PrimitiveTypes.int]))
    elif isinstance(e[-1], concat.level0.parse.NameWordNode):
        # the type of if_then is built-in
        if e[-1].value == 'if_then':
            S, (i, o) = infer(gamma, e[:-1])
            a_bar = SequenceVariable()
            b = IndividualVariable()
            phi = unify(o, [a_bar, b, b, PrimitiveTypes.bool])
            return phi(S), phi(_Function(i, [a_bar, b]))
        # the type of call is built-in
        elif e[-1].value == 'call':
            S, (i, o) = infer(gamma, e[:-1])
            a_bar, b_bar = SequenceVariable(), SequenceVariable()
            phi = unify(o, [a_bar, _Function([a_bar], [b_bar])])
            return phi(S), phi(_Function(i, [b_bar]))
        S, (i1, o1) = infer(gamma, e[:-1])
        if not e[-1].value in S(gamma):
            raise NameError(e[-1])
        type_of_name = _inst(S(gamma)[e[-1].value].to_for_all())
        if not isinstance(type_of_name, _Function):
            raise NotImplementedError(
                'name {} of type {}'.format(e[-1].value, type_of_name))
        i2, o2 = type_of_name
        print('name', repr(e[-1].value), 'at', e[-1].location)
        print('unifying', o1, 'with', S(i2))
        phi = unify(o1, S(i2))
        return phi(S), phi(_Function(i1, S(o2)))
    elif isinstance(e[-1], concat.level0.parse.PushWordNode):
        pushed = cast(concat.level0.parse.PushWordNode, e[-1])
        S1, (i1, o1) = infer(gamma, e[:-1])
        # special case for push an attribute accessor
        child = pushed.children[0]
        if isinstance(child, concat.level0.parse.AttributeWordNode):
            attr_type_var = IndividualVariable()
            top = IndividualVariable(TypeWithAttribute(
                child.value, attr_type_var))
            rest = SequenceVariable()
            S2 = unify(o1, [rest, top])
            attr_type = S2(attr_type_var)
            rest_types = S2(rest)
            if isinstance(rest_types, SequenceVariable):
                rest_types = [rest_types]
            return S2(S1), _Function(S2(i1), [*rest_types, attr_type])
        # special case for name words
        elif isinstance(child, concat.level0.parse.NameWordNode):
            name_type = gamma[child.value]
            return S1, _Function(i1, [*o1, S1(name_type)])
        S2, (i2, o2) = infer(S1(gamma), pushed.children)
        return S2(S1), _Function(S2(i1), [*S2(o1), _Function(i2, o2)])
    elif isinstance(e[-1], concat.level0.parse.QuoteWordNode):
        quotation = cast(concat.level0.parse.QuoteWordNode, e[-1])
        return infer(gamma, [*e[:-1], *quotation.children])
    # there is no fix combinator, lambda abstraction, or a let form like
    # Kleffner's
    # now for our extensions
    elif isinstance(e[-1], concat.level1.parse.WithWordNode):
        S, (i, o) = infer(gamma, e[:-1])
        a_bar, b_bar = SequenceVariable(), SequenceVariable()
        phi = unify(o, [a_bar, _Function([a_bar, PrimitiveTypes.object], [
            b_bar]), PrimitiveTypes.context_manager])
        return phi(S), phi(_Function(i, [b_bar]))
    elif isinstance(e[-1], concat.level1.parse.TryWordNode):
        S, (i, o) = infer(gamma, e[:-1])
        a_bar, b_bar = SequenceVariable(), SequenceVariable()
        phi = unify(o, [a_bar, PrimitiveTypes.iterable,
                        _Function([a_bar], [b_bar])])
        return phi(S), phi(_Function(i, [b_bar]))
    elif isinstance(e[-1], concat.level1.parse.FuncdefStatementNode):
        S, f = infer(gamma, e[:-1])
        name = e[-1].name
        declared_type = e[-1].stack_effect
        phi1, inferred_type = infer(S(gamma), e[-1].body)
        if declared_type is not None:
            declared_type = S(declared_type)
            phi2 = unify_ind(declared_type, inferred_type)
            if not phi2(declared_type).is_subtype_of(phi2(inferred_type)):
                message = ('declared function type {} is not compatible with '
                           'inferred type {}')
                raise TypeError(message.format(
                    declared_type, inferred_type))
            type = declared_type
        else:
            type = inferred_type
        # we *mutate* the type environment
        gamma[name] = type.generalized_wrt(S(gamma))
        return S, f
    elif isinstance(e[-1], concat.level1.parse.DictWordNode):
        S, (i, o) = infer(gamma, e[:-1])
        phi = S
        collected_type = o
        for key, value in e[-1].dict_children:
            phi1, (i1, o1) = infer(phi(gamma), key)
            R1 = unify(collected_type, i1)
            phi = R1(phi1(phi(S)))
            collected_type = phi(o1)
            # drop the top of the stack to use as the key
            collected_type, collected_type_sub = drop_last_from_type_seq(
                collected_type)
            phi = collected_type_sub(phi)
            phi2, (i2, o2) = infer(phi(gamma), value)
            R2 = unify(collected_type, i2)
            phi = R2(phi2)
            collected_type = phi(o2)
            # drop the top of the stack to use as the value
            collected_type, collected_type_sub = drop_last_from_type_seq(
                collected_type)
            phi = collected_type_sub(phi)
        return phi, phi(_Function(i, [*collected_type, PrimitiveTypes.dict]))
    elif isinstance(e[-1], concat.level1.parse.ListWordNode):
        S, (i, o) = infer(gamma, e[:-1])
        phi = S
        collected_type = o
        for item in e[-1].list_children:
            phi1, (i1, o1) = infer(phi(gamma), item)
            R1 = unify(collected_type, i1)
            collected_type = R1(phi1(phi(o1)))
            # drop the top of the stack to use as the key
            collected_type, collected_type_sub = drop_last_from_type_seq(
                collected_type)
            phi = collected_type_sub(R1(phi1(phi)))
        return phi, phi(_Function(i, [*collected_type, PrimitiveTypes.list]))
    elif isinstance(e[-1], concat.level1.parse.InvertWordNode):
        S, (i, o) = infer(gamma, e[:-1])
        out_var = SequenceVariable()
        type_var = IndividualVariable(PrimitiveInterfaces.invertible)
        phi = unify(o, [out_var, type_var])
        return phi(S), phi(_Function(i, [out_var, type_var]))
    elif isinstance(e[-1], concat.level0.parse.StringWordNode):
        S, (i, o) = infer(gamma, e[:-1])
        return S, _Function(i, [*o, PrimitiveTypes.str])
    elif isinstance(e[-1], concat.level0.parse.AttributeWordNode):
        S, (i, o) = infer(gamma, e[:-1])
        out_var = SequenceVariable()
        attr_type_var = IndividualVariable()
        type_var = IndividualVariable(
            TypeWithAttribute(e[-1].value, attr_type_var))
        phi = unify(o, [out_var, type_var])
        attr_type = phi(attr_type_var)
        if not isinstance(attr_type, _Function):
            print('type here is:', i, o)
            message = '.{} is not a Concat function (has type {})'.format(
                e[-1].value, attr_type)
            raise TypeError(message)
        out_types = phi(out_var)
        if isinstance(out_types, SequenceVariable):
            out_types = [out_types]
        R = unify(phi(o), [*out_types, *attr_type.input])
        return R(phi(S)), R(phi(_Function(i, attr_type.output)))
    else:
        for extension in infer._extensions:  # type: ignore
            try:
                return extension(gamma, e)
            except NotImplementedError as exc:
                print('NotImplementedError', exc)
                # print(exc.__traceback__)
                pass
        print(infer._extensions)
        raise NotImplementedError(
            "don't know how to handle '{}'".format(e[-1]))


# Initialize the extensions
infer._extensions = ()  # type: ignore


def _ftv(f: Union[Type, List[Type], Dict[str, Type]]) -> Set[_Variable]:
    """The ftv function described by Kleffner."""
    ftv: Set[_Variable]
    if isinstance(f, (_BuiltinType, PrimitiveInterface)):
        return set()
    elif isinstance(f, _Variable):
        return {f}
    elif isinstance(f, _Function):
        return _ftv(f.input) | _ftv(f.output)
    elif isinstance(f, list):
        ftv = set()
        for t in f:
            ftv |= _ftv(t)
        return ftv
    elif isinstance(f, ForAll):
        return _ftv(f.type) - set(f.quantified_variables)
    elif isinstance(f, dict):
        ftv = set()
        for sigma in f.values():
            ftv |= _ftv(sigma)
        return ftv
    elif isinstance(f, _IntersectionType):
        return _ftv(f.type_1) | _ftv(f.type_2)
    elif isinstance(f, TypeWithAttribute):
        return _ftv(f.attribute_type)
    else:
        raise builtins.TypeError(f)


def unify(i1: List[Type], i2: List[Type]) -> Substitutions:
    """The unify function described by Kleffner, but with support for subtyping.

    Since subtyping is a directional relation, we say i1 is the input type, and
    i2 is the output type. The subsitutions returned will make i1 a subtype of
    i2. This is inspired by Polymorphism, Subtyping, and Type Inference in
    MLsub (Dolan and Mycroft 2016)."""
    # TODO: Make this an abstract class.
    IndividualTypes = (_BuiltinType, IndividualVariable,
                       _Function, _IntersectionType, TypeWithAttribute, PrimitiveInterface)
    if (len(i1), len(i2)) == (0, 0):
        return Substitutions({})
    elif len(i1) == 1:
        if isinstance(i1[0], SequenceVariable) and i1 == i2:
            return Substitutions({})
        elif isinstance(i1[0], SequenceVariable) and i1[0] not in _ftv(i2):
            return Substitutions({i1[0]: i2})
    elif len(i2) == 1 and isinstance(i2[0], SequenceVariable) and \
            i2[0] not in _ftv(i1):
        return Substitutions({i2[0]: i1})
    elif len(i1) > 0 and len(i2) > 0 and \
            isinstance(i1[-1], IndividualTypes) and \
            isinstance(i2[-1], IndividualTypes):
        phi1 = unify_ind(i1[-1], i2[-1])
        phi2 = unify(phi1(i1[:-1]), phi1(i2[:-1]))
        return phi2(phi1)
    raise TypeError('cannot unify {} with {}'.format(i1, i2))


IndividualType = Union[_BuiltinType, IndividualVariable,
                       _Function, _IntersectionType, TypeWithAttribute, PrimitiveInterface]


def unify_ind(t1: IndividualType, t2: IndividualType) -> Substitutions:
    """A modified version of the unifyInd function described by Kleffner.

    Since subtyping is a directional relation, we say t1 is the input type, and
    t2 is the output type. The subsitutions returned will make t1 a subtype of
    t2. This is inspired by Polymorphism, Subtyping, and Type Inference in
    MLsub (Dolan and Mycroft 2016). Variables can be subsituted in either
    direction."""
    Primitive = (_BuiltinType, PrimitiveInterface)
    if isinstance(t1, Primitive) and isinstance(t2, Primitive):
        if not t1.is_subtype_of(t2):
            raise TypeError(
                'Primitive type {} cannot unify with primitive type {}'
                .format(t1, t2))
        return Substitutions()
    elif isinstance(t1, IndividualVariable) and t1 not in _ftv(t2):
        if t2.is_subtype_of(t1):
            return Substitutions({t1: t2})
        elif t1.is_subtype_of(t2):
            return Substitutions()
        raise TypeError('{} cannot unify with {}'.format(t1, t2))
    elif isinstance(t2, IndividualVariable) and t2 not in _ftv(t1):
        if t1.is_subtype_of(t2):
            return Substitutions({t2: t1})
        raise TypeError('{} cannot unify with {}'.format(t1, t2))
    elif isinstance(t1, _Function) and isinstance(t2, _Function):
        phi1 = unify(t1.input, t2.input)
        phi2 = unify(phi1(t1.output), phi1(t2.output))
        return phi2(phi1)
    else:
        raise NotImplementedError('How do I unify these?', t1, t2)


def drop_last_from_type_seq(l: List[Type]) -> Tuple[List[Type], Substitutions]:
    kept = SequenceVariable()
    dropped = IndividualVariable()
    drop_sub = unify(l, [kept, dropped])
    return drop_sub([kept]), drop_sub


def _ensure_type(
    typename: Union[Optional[concat.level0.lex.Token], _Function],
    env: Environment,
    obj_name: str
) -> Type:
    if obj_name in env:
        type = env[obj_name]
    elif typename is None:
        # TODO: If this is the output side of the stack effect, we should
        # default to object. Otherwise, we can end up with sn unbound type
        # variable which will be bound to the first type it's used as. That
        # could lead to some suprising behavior.
        type = IndividualVariable()
    elif isinstance(typename, _Function):
        type = typename
    else:
        type = getattr(PrimitiveTypes, typename.value)
    env[obj_name] = type
    return type


def _stack_effect(
    env: Environment
) -> 'parsy.Parser[concat.level0.lex.Token, _Function]':
    # TODO: Rewrite parser as a ParserDict extension.
    @parsy.generate('stack effect')
    def _stack_effect() -> Generator:
        parser_dict = concat.level0.parse.ParserDict()

        name = parser_dict.token('NAME')
        seq_var = parser_dict.token('STAR') >> name

        lpar = parser_dict.token('LPAR')
        rpar = parser_dict.token('RPAR')
        nested_stack_effect = lpar >> _stack_effect << rpar
        type = name | parser_dict.token('BACKTICK') >> name >> parsy.success(
            None) | nested_stack_effect
        separator = parser_dict.token('MINUS').times(2)

        item = parsy.seq(name, (parser_dict.token('COLON') >> type).optional())
        items = item.many()

        stack_effect = parsy.seq(  # type: ignore
            seq_var.optional(), items << separator, seq_var.optional(), items)

        a_bar_parsed, i, b_bar_parsed, o = yield stack_effect

        a_bar = SequenceVariable()
        b_bar = a_bar
        if a_bar_parsed is not None:
            if a_bar_parsed.value in env:
                a_bar = cast(SequenceVariable, env[a_bar_parsed.value])
            env[a_bar_parsed.value] = a_bar
        if b_bar_parsed is not None:
            print("explicit output sequence variable")
            if b_bar_parsed.value in env:
                b_bar = cast(SequenceVariable, env[b_bar_parsed.value])
            else:
                b_bar = SequenceVariable()

        in_types = [_ensure_type(item[1], env, item[0].value) for item in i]
        out_types = [_ensure_type(item[1], env, item[0].value) for item in o]
        return _Function([a_bar, *in_types], [b_bar, *out_types])

    return _stack_effect


def parse_stack_effect(tokens: List[concat.level0.lex.Token]) -> _Function:
    env = Environment()

    return _stack_effect(env).parse(tokens)
