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
    TypeVar,
    TYPE_CHECKING,
    overload,
    cast,
)
from typing_extensions import Protocol
import concat.level0.parse
import concat.level1.operators
import concat.level1.parse
from concat.level1.typecheck.constraints import Constraints


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
        return (
            'name "{}" not previously defined'.format(self._name)
            + location_info
        )


class AttributeError(TypeError, builtins.AttributeError):
    def __init__(self, type: 'Type', attribute: str) -> None:
        super().__init__(
            'object of type {} does not have attribute {}'.format(
                type, attribute
            )
        )
        self._type = type
        self._attribute = attribute


class UnhandledNodeTypeError(builtins.NotImplementedError):
    pass


_Result = TypeVar('_Result', covariant=True)


class _Substitutable(Protocol[_Result]):
    def apply_substitution(self, sub: 'Substitutions') -> _Result:
        pass


class Substitutions(Dict['_Variable', Union['Type', List['StackItemType']]]):

    _T = Union[
        _Substitutable[
            Union[
                'Substitutions',
                'Type',
                Sequence['StackItemType'],
                'Environment',
            ]
        ],
        Sequence['StackItemType'],
    ]
    _U = Union[
        'Substitutions', 'Type', Sequence['StackItemType'], 'Environment'
    ]

    @overload
    def __call__(
        self, arg: Sequence['StackItemType']
    ) -> List['StackItemType']:
        ...

    @overload
    def __call__(self, arg: _Substitutable[_Result]) -> _Result:
        ...

    def __call__(self, arg: '_T') -> '_U':
        from concat.level1.typecheck.types import TypeSequence

        if isinstance(arg, collections.abc.Sequence):
            subbed_types: List[StackItemType] = []
            for type in arg:
                subbed_type: Union[
                    StackItemType, Sequence[StackItemType]
                ] = self(type)
                if isinstance(
                    subbed_type, (collections.abc.Sequence, TypeSequence)
                ):
                    subbed_types += [*subbed_type]
                else:
                    subbed_types.append(subbed_type)
            return subbed_types
        return arg.apply_substitution(self)

    def _dom(self) -> Set['_Variable']:
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


from concat.level1.typecheck.types import (
    Type,
    IndividualVariable,
    StackEffect,
    ForAll,
    IndividualType,
    ObjectType,
    SequenceVariable,
    TypeWithAttribute,
    TypeSequence,
    StackItemType,
    QuotationType,
    bool_type,
    context_manager_type,
    dict_type,
    inst,
    int_type,
    _ftv,
    init_primitives,
    invertible_type,
    iterable_type,
    list_type,
    str_type,
    object_type,
    py_function_type,
)


class Environment(Dict[str, IndividualType]):
    def copy(self) -> 'Environment':
        return Environment(super().copy())

    def apply_substitution(self, sub: 'Substitutions') -> 'Environment':
        return Environment({name: sub(t) for name, t in self.items()})


# FIXME: This should be reset after each type checking each program/unit.
_global_constraints = Constraints()


# FIXME: I'm really passing around a bunch of state here. I could create an
# object to store it, or turn this algorithm into an object.
def infer(
    gamma: Environment,
    e: 'concat.astutils.WordsOrStatements',
    extensions: Optional[Tuple[Callable]] = None,
    is_top_level=False,
    source_dir='.',
    initial_stack: Optional[TypeSequence] = None,
) -> Tuple[Substitutions, StackEffect]:
    """The infer function described by Kleffner."""
    e = list(e)
    current_subs = Substitutions()
    if initial_stack is None:
        initial_stack = TypeSequence(
            [] if is_top_level else [SequenceVariable()]
        )
    current_effect = StackEffect(initial_stack, initial_stack)

    for node in e:
        try:
            S, (i, o) = current_subs, current_effect

            if isinstance(node, concat.level0.parse.NumberWordNode):
                if isinstance(node.value, int):
                    current_effect = StackEffect(i, [*o, int_type])
                else:
                    raise UnhandledNodeTypeError
            # there's no False word at the moment
            elif isinstance(node, concat.level1.parse.TrueWordNode):
                current_effect = StackEffect(i, [*o, bool_type])
            elif isinstance(node, concat.level1.operators.AddWordNode):
                # rules:
                # require object_type because the methods should return
                # NotImplemented for most types
                # FIXME: Make the rules safer... somehow

                # ... a b => (... {__add__(object) -> s} t)
                # ---
                # a b + => (... s)

                # ... a b => (... t {__radd__(object) -> s})
                # ---
                # a b + => (... s)
                *rest, type1, type2 = current_effect.output
                try_radd = False
                try:
                    add_type = type1.get_type_of_attribute('__add__')
                except AttributeError:
                    try_radd = True
                else:
                    if not isinstance(add_type, ObjectType):
                        raise TypeError(
                            '__add__ method of type {} is not of an object type, instead has type {}'.format(
                                type1, add_type
                            )
                        )
                    if add_type.head != py_function_type:
                        print('py_function_type', py_function_type)
                        print('add_type.head', add_type.head)
                        raise TypeError(
                            '__add__ method of type {} is not a Python function, instead it has type {}'.format(
                                type1, add_type
                            )
                        )
                    if [*add_type.type_arguments[0]] != [object_type]:
                        raise TypeError(
                            '__add__ method of type {} does not have type (object) -> `t, instead it has type {}'.format(
                                type1, add_type
                            )
                        )
                    current_effect = StackEffect(
                        current_effect.input,
                        [*rest, add_type.type_arguments[1]],
                    )
                if try_radd:
                    radd_type = type2.get_type_of_attribute('__radd__')
                    if (
                        not isinstance(radd_type, ObjectType)
                        or radd_type.head != py_function_type
                        or [*radd_type.type_arguments[0]] != [object_type]
                    ):
                        raise TypeError(
                            '__radd__ method of type {} does not have type (object) -> `t, instead it has type {}'.format(
                                type2, radd_type
                            )
                        )
                    current_effect = StackEffect(
                        current_effect.input,
                        [*rest, radd_type.type_arguments[1]],
                    )
            elif isinstance(node, concat.level0.parse.NameWordNode):
                # FIXME: if_then, call
                (i1, o1) = current_effect
                if node.value not in S(gamma):
                    raise NameError(node)
                type_of_name = inst(S(gamma)[node.value].to_for_all())
                if not isinstance(type_of_name, StackEffect):
                    raise UnhandledNodeTypeError(
                        'name {} of type {} (repr {!r})'.format(
                            node.value, type_of_name, type_of_name
                        )
                    )
                TypeSequence(o1).constrain(
                    TypeSequence(type_of_name.input),
                    _global_constraints,
                    polymorphic=True,
                )
                # For now, piggyback on substitutions
                constraint_subs = (
                    _global_constraints.equalities_as_substitutions()
                )
                current_subs = constraint_subs(current_subs)
                current_effect = current_subs(
                    StackEffect(i1, type_of_name.output)
                )
            elif isinstance(
                node, concat.level0.parse.PushWordNode
            ) and not isinstance(
                node.children[0], concat.level1.parse.SubscriptionWordNode
            ):
                S1, (i1, o1) = S, (i, o)
                # special case for push an attribute accessor
                child = node.children[0]
                if isinstance(child, concat.level0.parse.AttributeWordNode):
                    top = o1[-1]
                    attr_type = top.get_type_of_attribute(child.value)
                    rest_types = o1[:-1]
                    current_subs, current_effect = (
                        S1,
                        StackEffect(i1, [*rest_types, attr_type]),
                    )
                # special case for name words
                elif isinstance(child, concat.level0.parse.NameWordNode):
                    if child.value not in gamma:
                        raise NameError(child)
                    name_type = inst(gamma[child.value].to_for_all())
                    current_subs, current_effect = (
                        S1,
                        StackEffect(i1, [*o1, S1(name_type)]),
                    )
                else:
                    S2, fun_type = infer(
                        S1(gamma),
                        node.children,
                        extensions=extensions,
                        source_dir=source_dir,
                    )
                    current_subs, current_effect = (
                        S2(S1),
                        StackEffect(
                            S2(i1), [*S2(o1), QuotationType(fun_type)]
                        ),
                    )
            elif isinstance(node, concat.level0.parse.QuoteWordNode):
                quotation = cast(concat.level0.parse.QuoteWordNode, node)
                S1, (i1, o1) = infer(
                    gamma,
                    [*quotation.children],
                    extensions=extensions,
                    source_dir=source_dir,
                    initial_stack=TypeSequence(o),
                )
                current_subs, current_effect = (
                    S1(S),
                    S1(StackEffect(i, o1)),
                )
            # there is no fix combinator, lambda abstraction, or a let form
            # like Kleffner's
            # now for our extensions
            elif isinstance(node, concat.level1.parse.WithWordNode):
                a_bar, b_bar = SequenceVariable(), SequenceVariable()
                body_type = StackEffect([a_bar, object_type], [b_bar])
                _global_constraints.add(TypeSequence(o), TypeSequence([a_bar, body_type, context_manager_type]))
                phi = _global_constraints.equalities_as_substitutions()
                current_subs, current_effect = (
                    phi(S),
                    phi(StackEffect(i, [b_bar])),
                )
            elif isinstance(node, concat.level1.parse.TryWordNode):
                a_bar, b_bar = SequenceVariable(), SequenceVariable()
                phi = unify(
                    list(o),
                    [
                        a_bar,
                        iterable_type[StackEffect([a_bar], [b_bar]),],
                        StackEffect([a_bar], [b_bar]),
                    ],
                )
                current_subs, current_effect = (
                    phi(S),
                    phi(StackEffect(i, [b_bar])),
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
                    phi(StackEffect(i, [*collected_type, dict_type])),
                )
            elif isinstance(node, concat.level1.parse.ListWordNode):
                phi = S
                collected_type = o
                for item in node.list_children:
                    phi1, fun_type = infer(
                        phi(gamma),
                        item,
                        extensions=extensions,
                        source_dir=source_dir,
                    )
                    i_var, o_var = SequenceVariable(), SequenceVariable()
                    phi1 = unify_ind(fun_type, StackEffect([i_var], [o_var]))(
                        phi1
                    )
                    i1, o1 = phi1([i_var]), phi1([o_var])
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
                    phi(StackEffect(i, [*collected_type, list_type])),
                )
            elif isinstance(node, concat.level1.operators.InvertWordNode):
                out_var = SequenceVariable()
                type_var = IndividualVariable(invertible_type)
                phi = unify(list(o), [out_var, type_var])
                current_subs, current_effect = (
                    phi(S),
                    phi(StackEffect(i, [out_var, type_var])),
                )
            elif isinstance(node, concat.level0.parse.StringWordNode):
                current_subs, current_effect = (
                    S,
                    StackEffect(i, [*o, str_type]),
                )
            elif isinstance(node, concat.level0.parse.AttributeWordNode):
                out_var = SequenceVariable()
                attr_function_type = StackEffect(
                    [SequenceVariable()], [SequenceVariable()]
                )
                stack_top_type = TypeWithAttribute(
                    node.value, attr_function_type
                )
                phi = unify(list(o), [out_var, stack_top_type])
                attr_function_type = phi(attr_function_type)
                out_types = phi([out_var])
                R = unify(out_types, phi([*attr_function_type.input]))
                current_subs, current_effect = (
                    R(phi(S)),
                    R(phi(StackEffect(i, attr_function_type.output))),
                )
            else:
                fail = True
                original_error = None
                for extension in extensions or []:
                    try:
                        kwargs = dict(
                            extensions=extensions,
                            previous=(S, StackEffect(i, o)),
                            source_dir=source_dir,
                        )
                        # NOTE: Extension compose their results with the
                        # current effect (the `previous` keyword argument).
                        current_subs, current_effect = extension(
                            gamma, [node], is_top_level, **kwargs
                        )
                        fail = False
                        break
                    except UnhandledNodeTypeError as e:
                        original_error = e
                if fail:
                    raise UnhandledNodeTypeError(
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
    Primitive = (ObjectType,)
    if isinstance(t1, Primitive) and isinstance(t2, ObjectType):
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
    elif isinstance(t1, StackEffect) and isinstance(t2, StackEffect):
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
