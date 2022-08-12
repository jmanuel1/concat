"""The Concat type checker.

The type inference algorithm was originally based on the one described in
"Robert Kleffner: A Foundation for Typed Concatenative Languages, April 2017."
"""

import abc
import builtins
import collections.abc
import importlib
import sys
from typing import (
    Generator,
    Iterable,
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
import parsy
import concat.parse
import concat.operators


if TYPE_CHECKING:
    import concat.astutils
    from concat.typecheck.types import _Variable


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
        name: Union[concat.parse.NameWordNode, str],
        location: Optional[concat.astutils.Location] = None,
    ) -> None:
        if isinstance(name, concat.parse.NameWordNode):
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


class StackMismatchError(TypeError):
    def __init__(
        self, actual: 'TypeSequence', expected: 'TypeSequence'
    ) -> None:
        super().__init__(
            'The stack here is {}, but sequence type {} was expected'.format(
                actual, expected
            )
        )


class UnhandledNodeTypeError(builtins.NotImplementedError):
    pass


_Result = TypeVar('_Result', covariant=True)


class _Substitutable(Protocol[_Result]):
    def apply_substitution(self, sub: 'Substitutions') -> _Result:
        pass


class Substitutions(Dict['_Variable', 'Type']):
    def __call__(self, arg: _Substitutable[_Result]) -> _Result:
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


from concat.typecheck.types import (
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
    ellipsis_type,
    int_type,
    init_primitives,
    invertible_type,
    iterable_type,
    list_type,
    module_type,
    none_type,
    not_implemented_type,
    object_type,
    py_function_type,
    slice_type,
    str_type,
    subscriptable_type,
    subtractable_type,
    tuple_type,
)


class Environment(Dict[str, Type]):
    def copy(self) -> 'Environment':
        return Environment(super().copy())

    def apply_substitution(self, sub: 'Substitutions') -> 'Environment':
        return Environment({name: sub(t) for name, t in self.items()})


def check(
    environment: Environment,
    program: concat.astutils.WordsOrStatements,
    source_dir: str = '.',
) -> None:
    import concat.typecheck.preamble_types

    environment = Environment(
        {**concat.typecheck.preamble_types.types, **environment}
    )
    infer(environment, program, None, True, source_dir)


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

            if isinstance(node, concat.operators.AddWordNode):
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
                        current_effect.input, [*rest, add_type.output],
                    )
                if try_radd:
                    radd_type = type2.get_type_of_attribute('__radd__')
                    if (
                        not isinstance(radd_type, ObjectType)
                        or radd_type.head != py_function_type
                        or [*radd_type.type_arguments[0]] != [object_type]
                    ):
                        raise TypeError(
                            '__radd__ method of type {} does not have type (object) -> `t, instead it has type {} (left operand is of type {})'.format(
                                type2, radd_type, type1
                            )
                        )
                    current_effect = StackEffect(
                        current_effect.input, [*rest, radd_type.output],
                    )
            elif isinstance(node, concat.parse.PushWordNode):
                S1, (i1, o1) = S, (i, o)
                # special case for pushing an attribute accessor
                child = node.children[0]
                if isinstance(child, concat.parse.AttributeWordNode):
                    top = o1[-1]
                    attr_type = top.get_type_of_attribute(child.value)
                    rest_types = o1[:-1]
                    current_subs, current_effect = (
                        S1,
                        StackEffect(i1, [*rest_types, attr_type]),
                    )
                # special case for name words
                elif isinstance(child, concat.parse.NameWordNode):
                    if child.value not in gamma:
                        raise NameError(child)
                    name_type = gamma[child.value].instantiate()
                    current_effect = StackEffect(
                        current_effect.input,
                        [*current_effect.output, current_subs(name_type)],
                    )
                elif isinstance(child, concat.parse.SliceWordNode):
                    sliceable_object_type = o[-1]
                    # This doesn't match the evaluation order used by the
                    # transpiler.
                    # FIXME: Change the transpiler to fit the type checker.
                    sub1, start_effect = infer(
                        gamma,
                        list(child.start_children),
                        extensions=extensions,
                        source_dir=source_dir,
                        initial_stack=TypeSequence(o[:-1]),
                    )
                    start_type = start_effect.output[-1]
                    o = tuple(start_effect.output[:-1])
                    sub2, stop_effect = infer(
                        sub1(gamma),
                        list(child.stop_children),
                        extensions=extensions,
                        source_dir=source_dir,
                        initial_stack=TypeSequence(o),
                    )
                    stop_type = stop_effect.output[-1]
                    o = tuple(stop_effect.output[:-1])
                    sub3, step_effect = infer(
                        sub2(sub1(gamma)),
                        list(child.step_children),
                        extensions=extensions,
                        source_dir=source_dir,
                        initial_stack=TypeSequence(o),
                    )
                    step_type = step_effect.output[-1]
                    o = tuple(step_effect.output[:-1])
                    this_slice_type = slice_type[
                        start_type, stop_type, step_type
                    ]
                    getitem_type = sliceable_object_type.get_type_of_attribute(
                        '__getitem__'
                    )
                    getitem_type = getitem_type.get_type_of_attribute(
                        '__call__'
                    )
                    getitem_type = getitem_type.instantiate()
                    if (
                        not isinstance(getitem_type, PythonFunctionType)
                        or len(getitem_type.input) != 1
                    ):
                        raise TypeError(
                            '__getitem__ method of {} has incorrect type {}'.format(
                                node, getitem_type
                            )
                        )
                    getitem_type, overload_subs = getitem_type.select_overload(
                        (this_slice_type,)
                    )
                    result_type = getitem_type.output
                    current_subs = overload_subs(
                        sub3(sub2(sub1(current_subs)))
                    )
                    current_effect = current_subs(
                        StackEffect(i, [*o, result_type])
                    )
                # special case for subscription words
                elif isinstance(child, concat.parse.SubscriptionWordNode):
                    S2, (i2, o2) = infer(
                        current_subs(gamma),
                        child.children,
                        extensions=extensions,
                        is_top_level=False,
                        source_dir=source_dir,
                        initial_stack=current_effect.output,
                    )
                    # FIXME: Should be generic
                    subscriptable_interface = subscriptable_type[
                        int_type, IndividualVariable(),
                    ]

                    rest_var = SequenceVariable()
                    expected_o2 = TypeSequence(
                        [rest_var, subscriptable_interface, int_type,]
                    )
                    o2[-1].constrain(int_type)
                    getitem_type = (
                        o2[-2]
                        .get_type_of_attribute('__getitem__')
                        .instantiate()
                        .get_type_of_attribute('__call__')
                        .instantiate()
                    )
                    if not isinstance(getitem_type, PythonFunctionType):
                        raise TypeError(
                            '__getitem__ of type {} is not a Python function (has type {})'.format(
                                o2[-2], getitem_type
                            )
                        )
                    getitem_type, overload_subs = getitem_type.select_overload(
                        [int_type]
                    )
                    current_subs = overload_subs(S2(current_subs))
                    current_effect = current_subs(
                        StackEffect(
                            current_effect.input,
                            [*o2[:-2], getitem_type.output],
                        )
                    )
                else:
                    if (
                        isinstance(child, concat.parse.QuoteWordNode)
                        and child.input_stack_type is not None
                    ):
                        input_stack, _ = child.input_stack_type.to_type(gamma)
                    else:
                        # The majority of quotations I've written don't comsume
                        # anything on the stack, so make that the default.
                        input_stack = TypeSequence([SequenceVariable()])
                    S2, fun_type = infer(
                        S1(gamma),
                        child.children,
                        extensions=extensions,
                        source_dir=source_dir,
                        initial_stack=input_stack,
                    )
                    current_subs, current_effect = (
                        S2(S1),
                        StackEffect(
                            S2(TypeSequence(i1)),
                            [*S2(TypeSequence(o1)), QuotationType(fun_type)],
                        ),
                    )
            elif isinstance(node, concat.parse.WithWordNode):
                a_bar, b_bar = SequenceVariable(), SequenceVariable()
                body_type = StackEffect([a_bar, object_type], [b_bar])
                phi = current_effect.output.constrain_and_bind_supertype_variables(
                    TypeSequence([a_bar, body_type, context_manager_type]),
                    set(),
                )
                assert b_bar in phi
                current_subs, current_effect = (
                    phi(current_subs),
                    phi(
                        StackEffect(
                            current_effect.input, TypeSequence([b_bar])
                        )
                    ),
                )
            elif isinstance(node, concat.parse.TryWordNode):
                a_bar, b_bar = SequenceVariable(), SequenceVariable()
                phi = TypeSequence(o).constrain_and_bind_supertype_variables(
                    TypeSequence(
                        [
                            a_bar,
                            iterable_type[StackEffect([a_bar], [b_bar]),],
                            StackEffect([a_bar], [b_bar]),
                        ]
                    ),
                    set(),
                )
                assert b_bar in phi
                current_subs, current_effect = (
                    phi(S),
                    phi(StackEffect(i, [b_bar])),
                )
            elif isinstance(node, concat.parse.ListWordNode):
                phi = S
                collected_type = TypeSequence(o)
                element_type: IndividualType = object_type
                for item in node.list_children:
                    phi1, fun_type = infer(
                        phi(gamma),
                        item,
                        extensions=extensions,
                        source_dir=source_dir,
                        initial_stack=collected_type,
                    )
                    collected_type = fun_type.output
                    # FIXME: Infer the type of elements in the list based on
                    # ALL the elements.
                    if element_type == object_type:
                        assert isinstance(collected_type[-1], IndividualType)
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
            elif isinstance(node, concat.parse.TupleWordNode):
                phi = S
                collected_type = current_effect.output
                element_types: List[IndividualType] = []
                for item in node.tuple_children:
                    phi1, fun_type = infer(
                        phi(gamma),
                        item,
                        extensions=extensions,
                        source_dir=source_dir,
                        initial_stack=collected_type,
                    )
                    collected_type = fun_type.output
                    assert isinstance(collected_type[-1], IndividualType)
                    element_types.append(collected_type[-1])
                    # drop the top of the stack to use as the item
                    collected_type = collected_type[:-1]
                    phi = phi1(phi)
                current_subs, current_effect = (
                    phi,
                    phi(
                        StackEffect(
                            i,
                            [
                                *collected_type,
                                tuple_type[TypeSequence(element_types),],
                            ],
                        )
                    ),
                )
            elif isinstance(node, concat.operators.InvertWordNode):
                out_types = current_effect.output[:-1]
                invert_attr_type = current_effect.output[
                    -1
                ].get_type_of_attribute('__invert__')
                if not isinstance(invert_attr_type, PythonFunctionType):
                    raise TypeError(
                        '__invert__ of type {} must be a Python function'.format(
                            current_effect.output[-1]
                        )
                    )
                result_type = invert_attr_type.output
                current_effect = StackEffect(
                    current_effect.input, [*out_types, result_type]
                )
            elif isinstance(node, concat.parse.SliceWordNode):
                sliceable_object_type = o[-1]
                # This doesn't match the evaluation order used by the
                # transpiler.
                # FIXME: Change the transpiler to fit the type checker.
                sub1, start_effect = infer(
                    gamma,
                    list(node.start_children),
                    source_dir=source_dir,
                    initial_stack=TypeSequence(o[:-1]),
                )
                start_type = start_effect.output[-1]
                o = tuple(start_effect.output[:-1])
                sub2, stop_effect = infer(
                    sub1(gamma),
                    list(node.stop_children),
                    source_dir=source_dir,
                    initial_stack=TypeSequence(o),
                )
                stop_type = stop_effect.output[-1]
                o = tuple(stop_effect.output[:-1])
                sub3, step_effect = infer(
                    sub2(sub1(gamma)),
                    list(node.step_children),
                    source_dir=source_dir,
                    initial_stack=TypeSequence(o),
                )
                step_type = step_effect.output[-1]
                o = tuple(step_effect.output[:-1])
                this_slice_type = slice_type[start_type, stop_type, step_type]
                getitem_type = sliceable_object_type.get_type_of_attribute(
                    '__getitem__'
                )
                getitem_type = getitem_type.get_type_of_attribute('__call__')
                getitem_type = getitem_type.instantiate()
                if (
                    not isinstance(getitem_type, PythonFunctionType)
                    or len(getitem_type.input) != 1
                ):
                    raise TypeError(
                        '__getitem__ method of {} has incorrect type {}'.format(
                            node, getitem_type
                        )
                    )
                getitem_type, overload_subs = getitem_type.select_overload(
                    (this_slice_type,)
                )
                result_type = getitem_type.output
                current_subs = overload_subs(sub3(sub2(sub1(current_subs))))
                current_effect = overload_subs(
                    StackEffect(i, [*o, result_type])
                )
            elif isinstance(node, concat.parse.FromImportStatementNode):
                imported_name = node.asname or node.imported_name
                # mutate type environment
                gamma[imported_name] = object_type
                # We will try to find a more specific type.
                sys.path, old_path = [source_dir, *sys.path], sys.path
                module = importlib.import_module(node.value)
                sys.path = old_path
                # For now, assume the module's written in Python.
                try:
                    # TODO: Support star imports
                    gamma[imported_name] = current_subs(
                        getattr(module, '@@types')[node.imported_name]
                    )
                except (KeyError, builtins.AttributeError):
                    # attempt introspection to get a more specific type
                    if callable(getattr(module, node.imported_name)):
                        args_var = SequenceVariable()
                        gamma[imported_name] = ObjectType(
                            IndividualVariable(),
                            {
                                '__call__': py_function_type[
                                    TypeSequence([args_var]), object_type
                                ],
                            },
                            type_parameters=[args_var],
                            nominal=True,
                        )
            elif isinstance(node, concat.parse.ImportStatementNode):
                # TODO: Support all types of import correctly.
                if node.asname is not None:
                    gamma[node.asname] = current_subs(
                        _generate_type_of_innermost_module(
                            node.value, source_dir
                        ).generalized_wrt(current_subs(gamma))
                    )
                else:
                    imported_name = node.value
                    # mutate type environment
                    components = node.value.split('.')
                    # FIXME: This replaces whatever was previously imported. I really
                    # should implement namespaces properly.
                    gamma[components[0]] = current_subs(
                        _generate_module_type(
                            components, source_dir=source_dir
                        )
                    )
            elif isinstance(node, concat.parse.SubscriptionWordNode):
                seq = current_effect.output[:-1]
                index_type_var = IndividualVariable()
                result_type_var = IndividualVariable()
                subscriptable_interface = subscriptable_type[
                    index_type_var, result_type_var
                ]
                (index_subs, (index_input, index_output),) = infer(
                    gamma,
                    node.children,
                    initial_stack=current_effect.output,
                    extensions=extensions,
                )
                index_output_typeseq = index_output
                subs = index_output_typeseq[
                    -2
                ].constrain_and_bind_supertype_variables(
                    subscriptable_interface, set(),
                )(
                    index_subs(current_subs)
                )
                subs(index_output_typeseq[-1]).constrain(subs(index_type_var))

                result_type = subs(result_type_var).get_type_of_attribute(
                    '__call__'
                )
                if not isinstance(result_type, StackEffect):
                    raise TypeError(
                        'result of subscription is not callable as a Concat function (has type {})'.format(
                            result_type
                        )
                    )
                subs = index_output_typeseq[
                    :-2
                ].constrain_and_bind_supertype_variables(
                    result_type.input, set()
                )(
                    subs
                )

                current_subs, current_effect = (
                    subs,
                    subs(
                        StackEffect(current_effect.input, result_type.output)
                    ),
                )
            elif isinstance(node, concat.operators.SubtractWordNode):
                # FIXME: We should check if the other operand supports __rsub__ if the
                # first operand doesn't support __sub__.
                other_operand_type_var = IndividualVariable()
                result_type_var = IndividualVariable()
                subtractable_interface = subtractable_type[
                    other_operand_type_var, result_type_var
                ]
                seq_var = SequenceVariable()
                final_subs = current_effect.output.constrain_and_bind_supertype_variables(
                    TypeSequence(
                        [
                            seq_var,
                            subtractable_interface,
                            other_operand_type_var,
                        ]
                    ),
                    set(),
                )
                assert seq_var in final_subs
                current_subs, current_effect = (
                    final_subs(current_subs),
                    final_subs(
                        StackEffect(
                            current_effect.input, [seq_var, result_type_var]
                        )
                    ),
                )
            elif isinstance(node, concat.parse.FuncdefStatementNode):
                S = current_subs
                f = current_effect
                name = node.name
                declared_type: Optional[StackEffect]
                if node.stack_effect:
                    declared_type, _ = node.stack_effect.to_type(S(gamma))
                    declared_type = S(declared_type)
                else:
                    # NOTE: To continue the "bidirectional" bent, we will require a
                    # type annotation.
                    # TODO: Make the return types optional?
                    # FIXME: Should be a parse error.
                    raise TypeError(
                        'must have type annotation on function definition'
                    )
                recursion_env = gamma.copy()
                recursion_env[name] = declared_type.generalized_wrt(S(gamma))
                phi1, inferred_type = infer(
                    S(recursion_env),
                    node.body,
                    is_top_level=False,
                    extensions=extensions,
                    initial_stack=declared_type.input,
                )
                # We want to check that the inferred outputs are subtypes of
                # the declared outputs. Thus, inferred_type.output should be a subtype
                # declared_type.output.
                try:
                    inferred_type.output.constrain(declared_type.output)
                except TypeError:
                    message = (
                        'declared function type {} is not compatible with '
                        'inferred type {}'
                    )
                    raise TypeError(
                        message.format(declared_type, inferred_type)
                    )
                effect = declared_type
                # we *mutate* the type environment
                gamma[name] = effect.generalized_wrt(S(gamma))
            elif isinstance(
                node, concat.operators.GreaterThanOrEqualToWordNode
            ):
                a_type, b_type = current_effect.output[-2:]
                try:
                    ge_type = a_type.get_type_of_attribute('__ge__')
                    if not isinstance(ge_type, PythonFunctionType):
                        raise TypeError(
                            'method __ge__ of type {} should be a Python function'.format(
                                ge_type
                            )
                        )
                    _, current_subs = ge_type.select_overload([b_type])
                except TypeError:
                    le_type = b_type.get_type_of_attribute('__le__')
                    if not isinstance(le_type, PythonFunctionType):
                        raise TypeError(
                            'method __le__ of type {} should be a Python function'.format(
                                le_type
                            )
                        )
                    _, current_subs = le_type.select_overload([a_type])
                current_subs, current_effect = (
                    current_subs,
                    StackEffect(
                        current_effect.input,
                        TypeSequence([*current_effect.output[:-2], bool_type]),
                    ),
                )
            elif isinstance(
                node,
                (
                    concat.operators.IsWordNode,
                    concat.operators.AndWordNode,
                    concat.operators.OrWordNode,
                    concat.operators.EqualToWordNode,
                ),
            ):
                # TODO: I should be more careful here, since at least __eq__ can be
                # deleted, if I remember correctly.
                if not isinstance(
                    current_effect.output[-1], IndividualType
                ) or not isinstance(current_effect.output[-2], IndividualType):
                    raise StackMismatchError(
                        TypeSequence(current_effect.output),
                        TypeSequence([object_type, object_type]),
                    )
                current_effect = StackEffect(
                    current_effect.input,
                    TypeSequence([*current_effect.output[:-2], bool_type]),
                )
            elif isinstance(node, concat.parse.NumberWordNode):
                if isinstance(node.value, int):
                    current_effect = StackEffect(i, [*o, int_type])
                else:
                    raise UnhandledNodeTypeError
            elif isinstance(node, concat.parse.NameWordNode):
                (i1, o1) = current_effect
                if node.value not in current_subs(gamma):
                    raise NameError(node)
                type_of_name = current_subs(gamma)[node.value].instantiate()
                type_of_name = type_of_name.get_type_of_attribute('__call__')
                if not isinstance(type_of_name, StackEffect):
                    raise UnhandledNodeTypeError(
                        'name {} of type {} (repr {!r})'.format(
                            node.value, type_of_name, type_of_name
                        )
                    )
                constraint_subs = o1.constrain_and_bind_supertype_variables(
                    type_of_name.input, set()
                )
                current_subs = constraint_subs(current_subs)
                current_effect = current_subs(
                    StackEffect(i1, type_of_name.output)
                )
            elif isinstance(node, concat.parse.QuoteWordNode):
                quotation = cast(concat.parse.QuoteWordNode, node)
                # make sure any annotation matches the current stack
                if quotation.input_stack_type is not None:
                    input_stack, _ = quotation.input_stack_type.to_type(gamma)
                    S = TypeSequence(o).constrain_and_bind_supertype_variables(
                        input_stack, set(),
                    )(S)
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
            elif isinstance(node, concat.parse.StringWordNode):
                current_subs, current_effect = (
                    S,
                    StackEffect(
                        current_effect.input,
                        [*current_effect.output, str_type],
                    ),
                )
            elif isinstance(node, concat.parse.AttributeWordNode):
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
                R = TypeSequence(
                    out_types
                ).constrain_and_bind_supertype_variables(
                    attr_function_type.input, set(),
                )
                current_subs, current_effect = (
                    R(S),
                    R(StackEffect(i, attr_function_type.output)),
                )
            elif isinstance(node, concat.parse.CastWordNode):
                new_type, _ = node.type.to_type(gamma)
                rest = current_effect.output[:-1]
                current_effect = current_subs(
                    StackEffect(current_effect.input, [*rest, new_type])
                )
            else:
                raise UnhandledNodeTypeError(
                    "don't know how to handle '{}'".format(node)
                )
        except TypeError as e:
            e.set_location_if_missing(node.location)
            raise
    return current_subs, current_effect


# Parsing type annotations


class TypeNode(concat.parse.Node, abc.ABC):
    def __init__(self, location: concat.astutils.Location) -> None:
        self.location = location

    @abc.abstractmethod
    def to_type(self, env: Environment) -> Tuple[Type, Environment]:
        pass


class IndividualTypeNode(TypeNode, abc.ABC):
    @abc.abstractmethod
    def __init__(self, location: concat.astutils.Location) -> None:
        super().__init__(location)

    @abc.abstractmethod
    def to_type(self, env: Environment) -> Tuple[IndividualType, Environment]:
        pass


# A dataclass is not used here because making this a subclass of an abstract
# class does not work without overriding __init__ even when it's a dataclass.
class NamedTypeNode(TypeNode):
    def __init__(self, location: concat.astutils.Location, name: str) -> None:
        super().__init__(location)
        self.name = name

    def __repr__(self) -> str:
        return '{}({!r}, {!r})'.format(
            type(self).__qualname__, self.location, self.name
        )

    def to_type(self, env: Environment) -> Tuple[Type, Environment]:
        type = env.get(self.name, None)
        if type is None:
            raise NameError(self.name, self.location)
        return type, env


class IntersectionTypeNode(IndividualTypeNode):
    def __init__(
        self,
        location: concat.astutils.Location,
        type_1: IndividualTypeNode,
        type_2: IndividualTypeNode,
    ):
        super().__init__(location)
        self.type_1 = type_1
        self.type_2 = type_2

    def to_type(self, env: Environment) -> Tuple[IndividualType, Environment]:
        raise NotImplementedError('intersection types should longer exist')


class _GenericTypeNode(IndividualTypeNode):
    def __init__(
        self,
        location: concat.astutils.Location,
        generic_type: IndividualTypeNode,
        type_arguments: Sequence[IndividualTypeNode],
    ) -> None:
        super().__init__(location)
        self._generic_type = generic_type
        self._type_arguments = type_arguments

    def to_type(self, env: Environment) -> Tuple[IndividualType, Environment]:
        args = []
        for arg in self._type_arguments:
            arg_as_type, env = arg.to_type(env)
            args.append(arg_as_type)
        generic_type, env = self._generic_type.to_type(env)
        if isinstance(generic_type, ObjectType):
            return generic_type[args], env
        raise TypeError('{} is not a generic type'.format(generic_type))


class _TypeSequenceIndividualTypeNode(IndividualTypeNode):
    def __init__(
        self, args: Sequence[Union[concat.lex.Token, IndividualTypeNode]],
    ) -> None:
        if args[0] is None:
            location = args[1].location
        else:
            location = args[0].start
        super().__init__(location)
        self._name = None if args[0] is None else args[0].value
        self._type = args[1]

    # QUESTION: Should I have a separate space for the temporary associated names?
    def to_type(self, env: Environment) -> Tuple[IndividualType, Environment]:
        if self._name is None:
            return self._type.to_type(env)
        elif self._type is None:
            return env[self._name].to_type(env)
        elif self._name in env:
            raise TypeError(
                '{} is associated with a type more than once in this sequence of types'.format(
                    self._name
                )
            )
        else:
            type, env = self._type.to_type(env)
            env = env.copy()
            env[self._name] = type
            return type, env

    @property
    def name(self) -> Optional[str]:
        return self._name

    @property
    def type(self) -> Optional[IndividualTypeNode]:
        return self._type


class TypeSequenceNode(TypeNode):
    def __init__(
        self,
        location: Optional[concat.astutils.Location],
        seq_var: Optional[str],
        individual_type_items: Iterable[_TypeSequenceIndividualTypeNode],
    ) -> None:
        super().__init__(location or (-1, -1))
        self._sequence_variable = seq_var
        self._individual_type_items = tuple(individual_type_items)

    def to_type(self, env: Environment) -> Tuple[TypeSequence, Environment]:
        sequence: List[StackItemType] = []
        if self._sequence_variable is None:
            # implicit stack polymorphism
            sequence.append(SequenceVariable())
        elif self._sequence_variable not in env:
            env = env.copy()
            env[self._sequence_variable] = SequenceVariable()
            sequence.append(env[self._sequence_variable])
        for type_node in self._individual_type_items:
            type, env = type_node.to_type(env)
            sequence.append(type)
        return TypeSequence(sequence), env

    @property
    def sequence_variable(self) -> Optional[str]:
        return self._sequence_variable

    @property
    def individual_type_items(
        self,
    ) -> Sequence[_TypeSequenceIndividualTypeNode]:
        return self._individual_type_items


class StackEffectTypeNode(IndividualTypeNode):
    def __init__(
        self,
        location: concat.astutils.Location,
        input: TypeSequenceNode,
        output: TypeSequenceNode,
    ) -> None:
        super().__init__(location)
        self.input_sequence_variable = input.sequence_variable
        self.input = [(i.name, i.type) for i in input.individual_type_items]
        self.output_sequence_variable = output.sequence_variable
        self.output = [(o.name, o.type) for o in output.individual_type_items]

    def __repr__(self) -> str:
        return '{}({!r}, {!r}, {!r}, {!r}, location={!r})'.format(
            type(self).__qualname__,
            self.input_sequence_variable,
            self.input,
            self.output_sequence_variable,
            self.output,
            self.location,
        )

    def to_type(self, env: Environment) -> Tuple[StackEffect, Environment]:
        a_bar = SequenceVariable()
        b_bar = a_bar
        new_env = env.copy()
        if self.input_sequence_variable is not None:
            if self.input_sequence_variable in new_env:
                a_bar = cast(
                    SequenceVariable, new_env[self.input_sequence_variable],
                )
            new_env[self.input_sequence_variable] = a_bar
        if self.output_sequence_variable is not None:
            if self.output_sequence_variable in new_env:
                b_bar = cast(
                    SequenceVariable, new_env[self.output_sequence_variable],
                )
            else:
                b_bar = SequenceVariable()
                new_env[self.output_sequence_variable] = b_bar

        in_types = []
        for item in self.input:
            type, new_env = _ensure_type(item[1], new_env, item[0])
            in_types.append(type)
        out_types = []
        for item in self.output:
            type, new_env = _ensure_type(item[1], new_env, item[0])
            out_types.append(type)

        return StackEffect([a_bar, *in_types], [b_bar, *out_types]), new_env


def typecheck_extension(parsers: concat.parse.ParserDict) -> None:
    @parsy.generate
    def attribute_type_parser() -> Generator:
        location = (yield parsers.token('DOT')).start
        name = (yield parsers.token('NAME')).value
        yield parsers.token('COLON')
        type = yield parsers['type']
        raise NotImplementedError('better think about the syntax of this')

    @parsy.generate
    def named_type_parser() -> Generator:
        name_token = yield parsers.token('NAME')
        return NamedTypeNode(name_token.start, name_token.value)

    @parsy.generate
    def type_sequence_parser() -> Generator:
        name = parsers.token('NAME')
        individual_type_variable = (
            # FIXME: Keep track of individual type variables
            parsers.token('BACKTICK')
            >> name
            >> parsy.success(None)
        )
        lpar = parsers.token('LPAR')
        rpar = parsers.token('RPAR')
        nested_stack_effect = lpar >> parsers['stack-effect-type'] << rpar
        type = parsers['type'] | individual_type_variable | nested_stack_effect

        # TODO: Allow type-only items
        item = parsy.seq(
            name, (parsers.token('COLON') >> type).optional()
        ).map(_TypeSequenceIndividualTypeNode)
        items = item.many()

        seq_var = parsers.token('STAR') >> name
        seq_var_parsed, i = yield parsy.seq(seq_var.optional(), items)
        seq_var_value = None

        if seq_var_parsed is None and i:
            location = i[0].location
        elif seq_var_parsed is not None:
            location = seq_var_parsed.start
            seq_var_value = seq_var_parsed.value
        else:
            location = None

        return TypeSequenceNode(location, seq_var_value, i)

    @parsy.generate
    def stack_effect_type_parser() -> Generator:
        separator = parsers.token('MINUS').times(2)

        stack_effect = parsy.seq(  # type: ignore
            parsers['type-sequence'] << separator, parsers['type-sequence']
        )

        i, o = yield stack_effect

        # FIXME: Get the location
        return StackEffectTypeNode((0, 0), i, o)

    @parsy.generate
    def intersection_type_parser() -> Generator:
        yield parsers.token('AMPER')
        type_1 = yield parsers['type']
        type_2 = yield parsers['type']
        return IntersectionTypeNode(type_1.location, type_1, type_2)

    parsers['stack-effect-type'] = concat.parser_combinators.desc_cumulatively(
        stack_effect_type_parser, 'stack effect type'
    )

    @parsy.generate
    def generic_type_parser() -> Generator:
        type = yield parsers['nonparameterized-type']
        yield parsers.token('LSQB')
        type_arguments = yield parsers['type'].sep_by(
            parsers.token('COMMA'), min=1
        )
        yield parsers.token('RSQB')
        return _GenericTypeNode(type.location, type, type_arguments)

    # TODO: Parse type variables
    parsers['nonparameterized-type'] = parsy.alt(
        concat.parser_combinators.desc_cumulatively(
            intersection_type_parser, 'intersection type'
        ),
        concat.parser_combinators.desc_cumulatively(
            attribute_type_parser, 'attribute type'
        ),
        concat.parser_combinators.desc_cumulatively(
            named_type_parser, 'named type'
        ),
        parsers.ref_parser('stack-effect-type'),
    )

    parsers['type'] = parsy.alt(
        concat.parser_combinators.desc_cumulatively(
            generic_type_parser, 'generic type'
        ),
        parsers.ref_parser('nonparameterized-type'),
    )

    parsers['type-sequence'] = concat.parser_combinators.desc_cumulatively(
        type_sequence_parser, 'type sequence'
    )


_seq_var = SequenceVariable()


def _generate_type_of_innermost_module(
    qualified_name: str, source_dir
) -> StackEffect:
    # We resolve imports as if we are the source file.
    sys.path, old_path = [source_dir, *sys.path], sys.path
    try:
        module = importlib.import_module(qualified_name)
    except ModuleNotFoundError:
        raise TypeError(
            'module {} not found during type checking'.format(qualified_name)
        )
    finally:
        sys.path = old_path
    module_attributes = {}
    for name in dir(module):
        attribute_type = object_type
        if isinstance(getattr(module, name), int):
            attribute_type = int_type
        elif callable(getattr(module, name)):
            attribute_type = py_function_type
        module_attributes[name] = attribute_type
    module_t = ObjectType(
        IndividualVariable(),
        module_attributes,
        nominal_supertypes=[module_type],
    )
    return StackEffect([_seq_var], [_seq_var, module_type])


def _generate_module_type(
    components: Sequence[str], _full_name: Optional[str] = None, source_dir='.'
) -> ObjectType:
    if _full_name is None:
        _full_name = '.'.join(components)
    if len(components) > 1:
        module_t = ObjectType(
            IndividualVariable(),
            {
                components[1]: _generate_module_type(
                    components[1:], _full_name, source_dir
                )[_seq_var,],
            },
            nominal_supertypes=[module_type],
        )
        effect = StackEffect([_seq_var], [_seq_var, module_type])
        return ObjectType(
            IndividualVariable(), {'__call__': effect,}, [_seq_var]
        )
    else:
        innermost_type = _generate_type_of_innermost_module(
            _full_name, source_dir
        )
        return ObjectType(
            IndividualVariable(), {'__call__': innermost_type,}, [_seq_var]
        )


def _ensure_type(
    typename: Union[Optional[NamedTypeNode], StackEffectTypeNode],
    env: Environment,
    obj_name: str,
) -> Tuple[Type, Environment]:
    type: Type
    if obj_name in env:
        type = cast(StackItemType, env[obj_name])
    elif typename is None:
        # NOTE: This could lead type varibles in the output of a function that
        # are unconstrained. In other words, it would basically become an Any
        # type.
        type = IndividualVariable()
    elif isinstance(
        typename, (_GenericTypeNode, NamedTypeNode, StackEffectTypeNode)
    ):
        type, env = typename.to_type(env)
    else:
        raise NotImplementedError(
            'Cannot turn {!r} into a type'.format(typename)
        )
    env[obj_name] = type
    return type, env


init_primitives()
