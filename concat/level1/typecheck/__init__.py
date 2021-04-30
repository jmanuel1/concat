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
    PythonFunctionType,
    SequenceVariable,
    TypeSequence,
    StackItemType,
    QuotationType,
    bool_type,
    context_manager_type,
    dict_type,
    ellipsis_type,
    int_type,
    _ftv,
    init_primitives,
    invertible_type,
    iterable_type,
    list_type,
    none_type,
    not_implemented_type,
    object_type,
    py_function_type,
    str_type,
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
                (i1, o1) = current_effect
                if node.value not in S(gamma):
                    raise NameError(node)
                type_of_name = S(gamma)[node.value].instantiate()
                type_of_name = type_of_name.get_type_of_attribute('__call__')
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
                    name_type = gamma[child.value].instantiate()
                    current_subs, current_effect = (
                        S1,
                        StackEffect(i1, [*o1, S1(name_type)]),
                    )
                else:
                    if isinstance(node, concat.level0.parse.QuoteWordNode):
                        input_stack, _ = node.input_stack_type.to_type(gamma)
                    else:
                        # The majority of quotations I've written don't comsume
                        # anything on the stack, so make that the default.
                        input_stack = TypeSequence([])
                    S2, fun_type = infer(
                        S1(gamma),
                        node.children,
                        extensions=extensions,
                        source_dir=source_dir,
                        initial_stack=input_stack,
                    )
                    current_subs, current_effect = (
                        S2(S1),
                        StackEffect(
                            S2(i1), [*S2(o1), QuotationType(fun_type)]
                        ),
                    )
            elif isinstance(node, concat.level0.parse.QuoteWordNode):
                quotation = cast(concat.level0.parse.QuoteWordNode, node)
                # make sure any annotation matches the current stack
                if quotation.input_stack_type is not None:
                    input_stack = quotation.input_stack_type.to_type(gamma)
                    _global_constraints.add(TypeSequence(o), input_stack)
                else:
                    input_stack = TypeSequence(o)
                S1, (i1, o1) = infer(
                    gamma,
                    [*quotation.children],
                    extensions=extensions,
                    source_dir=source_dir,
                    initial_stack=input_stack,
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
                _global_constraints.add(
                    TypeSequence(o),
                    TypeSequence([a_bar, body_type, context_manager_type]),
                )
                phi = _global_constraints.equalities_as_substitutions()
                current_subs, current_effect = (
                    phi(S),
                    phi(StackEffect(i, [b_bar])),
                )
            elif isinstance(node, concat.level1.parse.TryWordNode):
                a_bar, b_bar = SequenceVariable(), SequenceVariable()
                _global_constraints.add(
                    TypeSequence(o),
                    TypeSequence(
                        [
                            a_bar,
                            iterable_type[StackEffect([a_bar], [b_bar]),],
                            StackEffect([a_bar], [b_bar]),
                        ]
                    ),
                )
                phi = _global_constraints.equalities_as_substitutions()
                current_subs, current_effect = (
                    phi(S),
                    phi(StackEffect(i, [b_bar])),
                )
            elif isinstance(node, concat.level1.parse.DictWordNode):
                phi = S
                collected_type = o
                for key, value in node.dict_children:
                    print('collected_type', collected_type)
                    phi1, (i1, o1) = infer(
                        phi(gamma),
                        key,
                        extensions=extensions,
                        source_dir=source_dir,
                        initial_stack=TypeSequence(collected_type),
                    )
                    _global_constraints.add(
                        TypeSequence(phi1(collected_type)), TypeSequence(i1)
                    )
                    phi = _global_constraints.equalities_as_substitutions()(
                        phi1(phi)
                    )
                    collected_type = phi(o1)
                    # drop the top of the stack to use as the key
                    collected_type, key_type = (
                        collected_type[:-1],
                        collected_type[-1],
                    )
                    phi2, (i2, o2) = infer(
                        phi(gamma),
                        value,
                        extensions=extensions,
                        source_dir=source_dir,
                        initial_stack=TypeSequence(collected_type),
                    )
                    _global_constraints.add(
                        TypeSequence(phi2(collected_type)), TypeSequence(i2)
                    )
                    phi = _global_constraints.equalities_as_substitutions()(
                        phi2(phi)
                    )
                    collected_type = phi(o2)
                    # drop the top of the stack to use as the value
                    collected_type, value_type = (
                        collected_type[:-1],
                        collected_type[-1],
                    )
                current_subs, current_effect = (
                    phi,
                    phi(StackEffect(i, [*collected_type, dict_type])),
                )
            elif isinstance(node, concat.level1.parse.ListWordNode):
                phi = S
                collected_type = o
                element_type = object_type
                for item in node.list_children:
                    phi1, fun_type = infer(
                        phi(gamma),
                        item,
                        extensions=extensions,
                        source_dir=source_dir,
                        initial_stack=TypeSequence(collected_type),
                    )
                    collected_type = fun_type.output
                    # FIXME: Infer the type of elements in the list based on
                    # ALL the elements.
                    if element_type == object_type:
                        element_type = collected_type[-1]
                    # drop the top of the stack to use as the item
                    collected_type = collected_type[:-1]
                    phi = phi1(phi)
                current_subs, current_effect = (
                    phi,
                    phi(
                        StackEffect(
                            i, [*collected_type, list_type[element_type,]]
                        )
                    ),
                )
            elif isinstance(node, concat.level1.operators.InvertWordNode):
                out_types = o[:-1]
                invert_attr_type = o[-1].get_type_of_attribute('__invert__')
                if not isinstance(invert_attr_type, PythonFunctionType):
                    raise TypeError(
                        '__invert__ of type {} must be a Python function'.format(
                            o[-1]
                        )
                    )
                result_type = invert_attr_type.type_arguments[1]
                current_subs, current_effect = (
                    S,
                    StackEffect(i, [*out_types, result_type]),
                )
            elif isinstance(node, concat.level0.parse.StringWordNode):
                current_subs, current_effect = (
                    S,
                    StackEffect(i, [*o, str_type]),
                )
            elif isinstance(node, concat.level0.parse.AttributeWordNode):
                stack_top_type = o[-1]
                out_types = o[:-1]
                attr_function_type = stack_top_type.get_type_of_attribute(
                    node.value
                ).instantiate()
                if not isinstance(attr_function_type, StackEffect):
                    raise UnhandledNodeTypeError(
                        'attribute {} of type {} (repr {!r})'.format(
                            node.value, attr_function_type, attr_function_type
                        )
                    )
                _global_constraints.add(
                    TypeSequence(out_types),
                    TypeSequence(attr_function_type.input),
                )
                R = _global_constraints.equalities_as_substitutions()
                current_subs, current_effect = (
                    R(S),
                    R(StackEffect(i, attr_function_type.output)),
                )
            elif isinstance(node, concat.level1.parse.NoneWordNode):
                current_effect = StackEffect(i, [*o, none_type])
            elif isinstance(node, concat.level1.parse.NotImplWordNode):
                current_effect = StackEffect(i, [*o, not_implemented_type])
            elif isinstance(node, concat.level1.parse.EllipsisWordNode):
                current_effect = StackEffect(i, [*o, ellipsis_type])
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
    current_subs = _global_constraints.equalities_as_substitutions()(
        current_subs
    )
    return current_subs, current_effect


init_primitives()
