"""The Concat type checker.

The type inference algorithm is based on the one described in "Robert Kleffner:
A Foundation for Typed Concatenative Languages, April 2017."
"""

import builtins
import collections.abc
from typing import (
    List,
    Set,
    Tuple,
    Dict,
    Union,
    Optional,
    Callable,
    Sequence,
    NoReturn,
    TypeVar,
    TYPE_CHECKING,
    overload,
    cast,
)
from typing_extensions import Protocol
import concat.level0.parse
import concat.level1.operators
import concat.level1.parse
from concat.level1.typecheck.types import Type, PrimitiveType, PrimitiveTypes, IndividualVariable, _Variable, _Function, ForAll, IndividualType, _IntersectionType, PrimitiveInterface, SequenceVariable, TypeWithAttribute, StackItemType, PrimitiveInterfaces, inst, _ftv, init_primitives, StackEffect


if TYPE_CHECKING:
    import concat.astutils


class StaticAnalysisError(Exception):
    def __init__(self, message: str) -> None:
        self._message = message
        self.location: Optional['concat.astutils.Location'] = None

    def set_location_if_missing(
        self, location: 'concat.astutils.Location'
    ) -> None:
        if not self.location:
            self.location = location

    def __str__(self) -> str:
        return '{} at {}'.format(self._message, self.location)


class TypeError(StaticAnalysisError, builtins.TypeError):
    pass


class NameError(StaticAnalysisError, builtins.NameError):
    def __init__(
        self,
        name: Union[concat.level0.parse.NameWordNode, str],
        location: Optional[concat.astutils.Location] = None,
    ) -> None:
        if isinstance(name, concat.level0.parse.NameWordNode):
            location = name.location
            name = name.value
        super().__init__(name)
        self._name = name
        self.location = location or self.location

    def __str__(self) -> str:
        location_info = ''
        if self.location:
            location_info = ' (error at {}:{})'.format(*self.location)
        return 'name "{}" not previously defined'.format(
            self._name
        ) + location_info


class AttributeError(TypeError, builtins.AttributeError):
    def __init__(self, type: 'Type', attribute: str) -> None:
        super().__init__(
            'object of type {} does not have attribute {}'.format(
                type, attribute
            )
        )
        self._type = type
        self._attribute = attribute


_Result = TypeVar('_Result', covariant=True)


class _Substitutable(Protocol[_Result]):
    def apply_substitution(self, sub: 'Substitutions') -> _Result:
        pass


class Substitutions(Dict[_Variable, Union[Type, List['StackItemType']]]):

    _T = Union[_Substitutable[Union['Substitutions', Type, Sequence[StackItemType], 'Environment']], Sequence[StackItemType]]
    _U = Union['Substitutions', Type, Sequence['StackItemType'], 'Environment']

    @overload
    def __call__(
        self, arg: Sequence['StackItemType']
    ) -> List['StackItemType']:
        ...

    @overload
    def __call__(self, arg: _Substitutable[_Result]) -> _Result:
        ...

    def __call__(self, arg: '_T') -> '_U':
        if isinstance(arg, collections.abc.Sequence):
            subbed_types: List[StackItemType] = []
            for type in arg:
                subbed_type: Union[StackItemType, Sequence[StackItemType]] = self(
                    type
                )
                if isinstance(subbed_type, collections.abc.Sequence):
                    subbed_types += subbed_type
                else:
                    subbed_types.append(subbed_type)
            return subbed_types
        return arg.apply_substitution(self)

    def _dom(self) -> Set[_Variable]:
        return {*self}

    def __str__(self) -> str:
        return (
            '{'
            + ',\n'.join(
                map(lambda i: '{}: {}'.format(i[0], i[1]), self.items())
            )
            + '}'
        )

    def apply_substitution(self, sub: 'Substitutions') -> 'Substitutions':
        return Substitutions(
            {
                **sub,
                **{a: sub(i) for a, i in self.items() if a not in sub._dom()},
            }
        )


class Environment(Dict[str, Type]):
    def copy(self) -> 'Environment':
        return Environment(super().copy())

    def apply_substitution(self, sub: 'Substitutions') -> 'Environment':
        return Environment({name: sub(t) for name, t in self.items()})


def infer(
    gamma: Environment,
    e: 'concat.astutils.WordsOrStatements',
    extensions: Optional[Tuple[Callable]] = None,
    is_top_level=False,
    source_dir='.',
) -> Tuple[Substitutions, _Function]:
    """The infer function described by Kleffner."""
    e = list(e)
    current_subs = Substitutions()
    a_bar = SequenceVariable()
    current_effect = (
        _Function([], []) if is_top_level else _Function([a_bar], [a_bar])
    )

    for node in e:
        try:
            S, (i, o) = current_subs, current_effect

            if isinstance(node, concat.level0.parse.NumberWordNode):
                if isinstance(node.value, int):
                    current_effect = _Function(i, [*o, PrimitiveTypes.int])
                else:
                    raise NotImplementedError
            # there's no False word at the moment
            elif isinstance(node, concat.level1.parse.TrueWordNode):
                current_effect = _Function(i, [*o, PrimitiveTypes.bool])
            elif isinstance(node, concat.level1.operators.AddWordNode):
                # for now, only works with ints and strings
                a_bar = SequenceVariable()
                try:
                    phi = unify(
                        list(o),
                        [a_bar, PrimitiveTypes.int, PrimitiveTypes.int],
                    )
                except TypeError:
                    phi = unify(
                        list(o),
                        [a_bar, PrimitiveTypes.str, PrimitiveTypes.str],
                    )
                    current_subs, current_effect = (
                        phi(S),
                        phi(_Function(i, [a_bar, PrimitiveTypes.str])),
                    )
                else:
                    current_subs, current_effect = (
                        phi(S),
                        phi(_Function(i, [a_bar, PrimitiveTypes.int])),
                    )
            elif isinstance(node, concat.level0.parse.NameWordNode):
                # the type of if_then is built-in
                if node.value == 'if_then':
                    a_bar = SequenceVariable()
                    b = _Function([a_bar], [a_bar])
                    phi = unify(list(o), [a_bar, PrimitiveTypes.bool, b])
                    current_subs, current_effect = (
                        phi(S),
                        phi(_Function(i, [a_bar])),
                    )
                # the type of call is built-in
                elif node.value == 'call':
                    a_bar, b_bar = SequenceVariable(), SequenceVariable()
                    phi = unify(list(o), [a_bar, _Function([a_bar], [b_bar])])
                    current_subs, current_effect = (
                        phi(S),
                        phi(_Function(i, [b_bar])),
                    )
                else:
                    (i1, o1) = i, o
                    if node.value not in S(gamma):
                        raise NameError(node)
                    type_of_name = inst(S(gamma)[node.value].to_for_all())
                    if not isinstance(type_of_name, _Function):
                        raise NotImplementedError(
                            'name {} of type {} (repr {!r})'.format(
                                node.value, type_of_name, type_of_name
                            )
                        )
                    i2, o2 = type_of_name
                    phi = unify(list(o1), S(i2))
                    current_subs, current_effect = (
                        phi(S),
                        phi(_Function(i1, S(o2))),
                    )
            elif isinstance(
                node, concat.level0.parse.PushWordNode
            ) and not isinstance(
                node.children[0], concat.level1.parse.SubscriptionWordNode
            ):
                S1, (i1, o1) = S, (i, o)
                # special case for push an attribute accessor
                child = node.children[0]
                rest = SequenceVariable()
                if isinstance(child, concat.level0.parse.AttributeWordNode):
                    attr_type_var = IndividualVariable()
                    top = IndividualVariable(
                        TypeWithAttribute(child.value, attr_type_var)
                    )
                    S2 = unify(list(o1), [rest, top])
                    attr_type = inst(S2(attr_type_var).to_for_all())
                    rest_types = S2([rest])
                    current_subs, current_effect = (
                        S2(S1),
                        _Function(S2(i1), [*rest_types, attr_type]),
                    )
                # special case for name words
                elif isinstance(child, concat.level0.parse.NameWordNode):
                    if child.value not in gamma:
                        raise NameError(child)
                    name_type = inst(gamma[child.value].to_for_all())
                    current_subs, current_effect = (
                        S1,
                        _Function(i1, [*o1, S1(name_type)]),
                    )
                else:
                    S2, (i2, o2) = infer(
                        S1(gamma),
                        node.children,
                        extensions=extensions,
                        source_dir=source_dir,
                    )
                    current_subs, current_effect = (
                        S2(S1),
                        _Function(S2(i1), [*S2(o1), _Function(i2, o2)]),
                    )
            elif isinstance(node, concat.level0.parse.QuoteWordNode):
                quotation = cast(concat.level0.parse.QuoteWordNode, node)
                S1, (i1, o1) = infer(
                    gamma,
                    [*quotation.children],
                    extensions=extensions,
                    source_dir=source_dir,
                )
                phi = unify(S1(o), i1)
                current_subs, current_effect = (
                    phi(S1(S)),
                    phi(S1(_Function(i, o1))),
                )
            # there is no fix combinator, lambda abstraction, or a let form like
            # Kleffner's
            # now for our extensions
            elif isinstance(node, concat.level1.parse.WithWordNode):
                a_bar, b_bar = SequenceVariable(), SequenceVariable()
                body_type = _Function([a_bar, PrimitiveTypes.object], [b_bar])
                phi = unify(
                    list(o), [a_bar, body_type, PrimitiveTypes.context_manager]
                )
                current_subs, current_effect = (
                    phi(S),
                    phi(_Function(i, [b_bar])),
                )
            elif isinstance(node, concat.level1.parse.TryWordNode):
                a_bar, b_bar = SequenceVariable(), SequenceVariable()
                phi = unify(
                    list(o),
                    [
                        a_bar,
                        PrimitiveInterfaces.iterable,
                        _Function([a_bar], [b_bar]),
                    ],
                )
                current_subs, current_effect = (
                    phi(S),
                    phi(_Function(i, [b_bar])),
                )
            elif isinstance(node, concat.level1.parse.DictWordNode):
                phi = S
                collected_type = o
                for key, value in node.dict_children:
                    phi1, (i1, o1) = infer(
                        phi(gamma),
                        key,
                        extensions=extensions,
                        source_dir=source_dir,
                    )
                    R1 = unify(phi1(collected_type), list(i1))
                    phi = R1(phi1(phi))
                    collected_type = phi(o1)
                    # drop the top of the stack to use as the key
                    (
                        collected_type,
                        collected_type_sub,
                    ) = drop_last_from_type_seq(collected_type)
                    phi = collected_type_sub(phi)
                    phi2, (i2, o2) = infer(
                        phi(gamma),
                        value,
                        extensions=extensions,
                        source_dir=source_dir,
                    )
                    R2 = unify(phi2(collected_type), list(i2))
                    phi = R2(phi2(phi))
                    collected_type = phi(o2)
                    # drop the top of the stack to use as the value
                    (
                        collected_type,
                        collected_type_sub,
                    ) = drop_last_from_type_seq(collected_type)
                    phi = collected_type_sub(phi)
                current_subs, current_effect = (
                    phi,
                    phi(_Function(i, [*collected_type, PrimitiveTypes.dict])),
                )
            elif isinstance(node, concat.level1.parse.ListWordNode):
                phi = S
                collected_type = o
                for item in node.list_children:
                    phi1, (i1, o1) = infer(
                        phi(gamma),
                        item,
                        extensions=extensions,
                        source_dir=source_dir,
                    )
                    R1 = unify(phi1(phi(collected_type)), list(i1))
                    collected_type = R1(phi1(phi(o1)))
                    # drop the top of the stack to use as the key
                    (
                        collected_type,
                        collected_type_sub,
                    ) = drop_last_from_type_seq(list(collected_type))
                    phi = collected_type_sub(R1(phi1(phi)))
                current_subs, current_effect = (
                    phi,
                    phi(_Function(i, [*collected_type, PrimitiveTypes.list])),
                )
            elif isinstance(node, concat.level1.operators.InvertWordNode):
                out_var = SequenceVariable()
                type_var = IndividualVariable(PrimitiveInterfaces.invertible)
                phi = unify(list(o), [out_var, type_var])
                current_subs, current_effect = (
                    phi(S),
                    phi(_Function(i, [out_var, type_var])),
                )
            elif isinstance(node, concat.level0.parse.StringWordNode):
                current_subs, current_effect = (
                    S,
                    _Function(i, [*o, PrimitiveTypes.str]),
                )
            elif isinstance(node, concat.level0.parse.AttributeWordNode):
                out_var = SequenceVariable()
                attr_type_var = IndividualVariable()
                type_var = IndividualVariable(
                    TypeWithAttribute(node.value, attr_type_var)
                )
                phi = unify(list(o), [out_var, type_var])
                attr_type = phi(attr_type_var)
                if not isinstance(attr_type, _Function):
                    message = '.{} is not a Concat function (has type {})'.format(
                        node.value, attr_type
                    )
                    raise TypeError(message)
                out_types = phi(out_var)
                if isinstance(out_types, SequenceVariable):
                    out_types = [out_types]
                R = unify(out_types, phi([*attr_type.input]))
                current_subs, current_effect = (
                    R(phi(S)),
                    R(phi(_Function(i, attr_type.output))),
                )
            else:
                fail = True
                original_error = None
                for extension in extensions or []:
                    try:
                        kwargs = dict(
                            extensions=extensions,
                            previous=(S, _Function(i, o)),
                            source_dir=source_dir,
                        )
                        # NOTE: Extension compose their results with the
                        # current effect (the `previous` keyword argument).
                        current_subs, current_effect = extension(
                            gamma, [node], is_top_level, **kwargs
                        )
                        fail = False
                        break
                    except NotImplementedError as e:
                        original_error = e
                if fail:
                    raise NotImplementedError(
                        "don't know how to handle '{}'".format(node)
                    ) from original_error
        except TypeError as e:
            e.set_location_if_missing(node.location)
            raise
    return current_subs, current_effect


def unify(i1: List[StackItemType], i2: List[StackItemType]) -> Substitutions:
    """The unify function described by Kleffner, but with support for subtyping.

    Since subtyping is a directional relation, we say i1 is the input type, and
    i2 is the output type. The subsitutions returned will make i1 a subtype of
    i2. This is inspired by Polymorphism, Subtyping, and Type Inference in
    MLsub (Dolan and Mycroft 2016)."""

    if (len(i1), len(i2)) == (0, 0):
        return Substitutions({})
    if len(i1) == 1:
        if isinstance(i1[0], SequenceVariable) and i1 == i2:
            return Substitutions({})
        elif isinstance(i1[0], SequenceVariable) and i1[0] not in _ftv(i2):
            return Substitutions({i1[0]: [*i2]})
    if (
        len(i2) == 1
        and isinstance(i2[0], SequenceVariable)
        and i2[0] not in _ftv(i1)
    ):
        return Substitutions({i2[0]: [*i1]})
    if (
        len(i1) > 0
        and len(i2) > 0
        and isinstance(i1[-1], IndividualType)
        and isinstance(i2[-1], IndividualType)
    ):
        phi1 = unify_ind(i1[-1], i2[-1])
        phi2 = unify(phi1(i1[:-1]), phi1(i2[:-1]))
        return phi2(phi1)
    raise TypeError(
        'cannot unify {} with {}'.format(
            ', '.join(str(t) for t in i1), ', '.join(str(t) for t in i2)
        )
    )


def unify_ind(
    t1: Union[IndividualType, ForAll], t2: Union[IndividualType, ForAll]
) -> Substitutions:
    """A modified version of the unifyInd function described by Kleffner.

    Since subtyping is a directional relation, we say t1 is the input type, and
    t2 is the output type. The subsitutions returned will make t1 a subtype of
    t2. This is inspired by Polymorphism, Subtyping, and Type Inference in
    MLsub (Dolan and Mycroft 2016). Variables can be subsituted in either
    direction."""
    t1 = inst(t1.to_for_all())
    t2 = inst(t2.to_for_all())
    Primitive = (PrimitiveType, PrimitiveInterface)
    if isinstance(t1, PrimitiveInterface) and isinstance(
        t2, PrimitiveInterface
    ):
        if not t1.is_related_to(t2):
            raise TypeError(
                '{} and {} are not derived from the same interface'.format(
                    t1, t2
                )
            )
        if t2.type_arguments is None:
            return Substitutions()
        if t1.type_arguments is None:
            raise TypeError(
                '{} has no type arguments, but {} does'.format(t1, t2)
            )
        return unify([*t1.type_arguments], [*t2.type_arguments])
    elif isinstance(t1, PrimitiveType) and isinstance(t2, PrimitiveInterface):
        phi = Substitutions()
        fail = True
        for type in t1.supertypes:
            try:
                phi = unify_ind(type, t2)(phi)
                fail = False
            except TypeError:
                pass
        if fail:
            raise TypeError('{} does not implement {}'.format(t1, t2))
        return phi
    elif isinstance(t1, Primitive) and isinstance(t2, PrimitiveType):
        # TODO: Unify type arguments
        if not t1.is_subtype_of(t2):
            raise TypeError(
                'Primitive type {} cannot unify with primitive type {}'.format(
                    t1, t2
                )
            )
        return Substitutions()
    elif isinstance(t1, IndividualVariable) and t1 not in _ftv(t2):
        phi = None
        if t1.is_subtype_of(t2):
            if isinstance(t2, IndividualVariable):
                phi = unify_ind(t1.bound, t2.bound)
            else:
                phi = unify_ind(t1.bound, t2)
        if t2.is_subtype_of(t1):
            phi = Substitutions({t1: IndividualVariable(t2)})(
                phi or Substitutions()
            )
        if phi is None:
            if isinstance(t2, IndividualVariable):
                new_var = IndividualVariable(t1.bound & t2.bound)
                phi = Substitutions({t1: new_var, t2: new_var})
            else:
                raise TypeError('{} cannot unify with {}'.format(t1, t2))

        return phi
    elif isinstance(t2, IndividualVariable) and t2 not in _ftv(t1):
        if t1.is_subtype_of(t2):
            phi = Substitutions({t2: t1})
            phi = (unify_ind(phi(t1), phi(t2.bound)))(phi)
            return phi
        raise TypeError('{} cannot unify with {}'.format(t1, t2))
    elif isinstance(t1, _Function) and isinstance(t2, _Function):
        phi1 = unify(list(t2.input), list(t1.input))
        phi2 = unify(list(phi1(t1.output)), list(phi1(t2.output)))
        return phi2(phi1)
    elif isinstance(t1, TypeWithAttribute):
        if t1.is_subtype_of(t2):
            try:
                attr_type = t2.get_type_of_attribute(t1.attribute)
            except TypeError:
                return Substitutions()
            return unify_ind(t1.attribute_type, attr_type)
        raise TypeError('{} cannot unify with {}'.format(t1, t2))
    elif isinstance(t2, TypeWithAttribute):
        attr_type = t1.get_type_of_attribute(t2.attribute)
        return unify_ind(attr_type, t2.attribute_type)
    elif t1.is_subtype_of(t2):
        return Substitutions()
    else:
        raise TypeError('{} cannot unify with {}'.format(t1, t2))


def drop_last_from_type_seq(
    l: List[StackItemType],
) -> Tuple[List[StackItemType], Substitutions]:
    kept = SequenceVariable()
    dropped = IndividualVariable()
    drop_sub = unify(l, [kept, dropped])
    return drop_sub([kept]), drop_sub


init_primitives()
