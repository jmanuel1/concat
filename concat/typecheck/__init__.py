"""The Concat type checker.

The type inference algorithm was originally based on the one described in
"Robert Kleffner: A Foundation for Typed Concatenative Languages, April 2017."
"""

from __future__ import annotations

import abc
import itertools
import pathlib
import sys
from collections.abc import Generator
from typing import (
    TYPE_CHECKING,
    Any,
    Callable,
    Dict,
    Iterable,
    List,
    Optional,
    Sequence,
    Tuple,
    Union,
    assert_never,
    cast,
)

import concat.graph
import concat.parse
import concat.parser_combinators
import concat.typecheck.preamble_types
from concat.error_reporting import (
    create_indentation_error_message,
    create_lexical_error_message,
    create_parsing_failure_message,
)
from concat.lex import Token
from concat.set_once import SetOnce
from concat.typecheck.env import Environment
from concat.typecheck.errors import (
    NameError,
    StaticAnalysisError,
    TypeError,
    UnhandledNodeTypeError,
    format_cannot_find_module_from_source_dir_error,
    format_cannot_find_module_path_error,
    format_decorator_result_kind_error,
    format_expected_item_kinded_variable_error,
    format_item_type_expected_in_type_sequence_error,
    format_name_reassigned_in_type_sequence_error,
    format_not_a_variable_error,
    format_not_generic_type_error,
    format_too_many_params_for_variadic_type_error,
)
from concat.typecheck.substitutions import Substitutions
from concat.typecheck.types import (
    BoundVariable,
    Brand,
    Fix,
    GenericType,
    GenericTypeKind,
    IndividualKind,
    IndividualType,
    ItemKind,
    ItemVariable,
    Kind,
    NominalType,
    ObjectType,
    QuotationType,
    SequenceVariable,
    StackEffect,
    TupleKind,
    Type,
    TypeSequence,
    TypeTuple,
    Variable,
    VariableArgumentKind,
    no_return_type,
)

if TYPE_CHECKING:
    import concat.astutils


_builtins_stub_path = pathlib.Path(__file__) / '../builtin_stubs/builtins.cati'


class TypeChecker:
    def __init__(self) -> None:
        self._module_namespaces: dict[pathlib.Path, Environment] = {}
        self._is_in_forward_references_phase = False

    def load_builtins_and_preamble(self) -> Environment:
        env = self._check_stub(
            pathlib.Path(__file__).with_name('preamble0.cati'),
        )
        env = self._check_stub(_builtins_stub_path, initial_env=env)
        env = self._check_stub(
            pathlib.Path(__file__).with_name('preamble.cati'),
            initial_env=env,
        )
        # pick up ModuleType
        return self._check_stub(
            _builtins_stub_path.with_name('types.cati'),
            initial_env=env,
        )

    def _check_stub(
        self,
        path: pathlib.Path,
        initial_env: Optional['Environment'] = None,
    ) -> 'Environment':
        path = path.resolve()
        return self._check_stub_resolved_path(path, initial_env)

    def _check_stub_resolved_path(
        self,
        path: pathlib.Path,
        initial_env: Optional['Environment'] = None,
    ) -> 'Environment':
        if path in self._module_namespaces:
            return self._module_namespaces[path]
        try:
            source = path.read_text()
        except FileNotFoundError as e:
            raise TypeError(
                f'Type stubs at {path} do not exist',
                is_occurs_check_fail=None,
                rigid_variables=None,
            ) from e
        except IOError as e:
            raise TypeError(
                f'Failed to read type stubs at {path}',
                is_occurs_check_fail=None,
                rigid_variables=None,
            ) from e
        token_results = concat.lex.tokenize(source)
        tokens = list[Token]()
        with path.open() as f:
            for r in token_results:
                if r.type == 'token':
                    tokens.append(r.token)
                elif r.type == 'indent-err':
                    print('Indentation error:')
                    print(
                        create_indentation_error_message(
                            f,
                            (r.err.lineno or 1, r.err.offset or 0),
                            r.err.msg,
                        )
                    )
                elif r.type == 'token-err':
                    print('Lexical error:')
                    print(
                        create_lexical_error_message(f, r.location, str(r.err))
                    )
                else:
                    assert_never(r)
        env = initial_env or Environment()
        from concat.transpile import parse

        try:
            concat_ast = parse(tokens)
        except concat.parser_combinators.ParseError as e:
            print('Parse Error:')
            with path.open() as file:
                print(
                    create_parsing_failure_message(
                        file, tokens, e.args[0].failures
                    )
                )
            self._module_namespaces[path] = env
            return env
        recovered_parsing_failures = concat_ast.parsing_failures
        with path.open() as file:
            for failure in recovered_parsing_failures:
                print('Parse Error:')
                print(create_parsing_failure_message(file, tokens, failure))
        try:
            env = self.check(
                env,
                concat_ast.children,
                str(path.parent),
                _should_check_bodies=False,
            )
        except StaticAnalysisError as e:
            e.set_path_if_missing(path)
            raise
        self._module_namespaces[path] = env
        return env

    # FIXME: I'm really passing around a bunch of state here. I could create an
    # object to store it, or turn this algorithm into an object.
    def infer(
        self,
        gamma: Environment,
        e: Sequence[concat.parse.Node],
        extensions: Optional[Tuple[Callable]] = None,
        is_top_level=False,
        source_dir='.',
        initial_stack: Optional[TypeSequence] = None,
        check_bodies: bool = True,
    ) -> Tuple[Substitutions, StackEffect, Environment]:
        """The infer function described by Kleffner."""
        e = list(e)
        current_subs = Substitutions()
        if initial_stack is None:
            initial_stack = TypeSequence(
                [] if is_top_level else [SequenceVariable()]
            )
        current_effect = StackEffect(initial_stack, initial_stack)

        # Prepare for forward references.
        # TODO: Do this in a more principled way with scope graphs.
        self._is_in_forward_references_phase = True
        ids_to_defs: dict[int, concat.parse.ClassdefStatementNode] = {}
        names_to_defs: dict[str, int] = {}
        ref_edges: list[tuple[int, int]] = []
        next_id = 0
        try:
            for node in e:
                if isinstance(node, concat.parse.ClassdefStatementNode):
                    ids_to_defs[next_id] = node
                    names_to_defs[node.class_name] = next_id
                    next_id += 1
            for def_id, node in ids_to_defs.items():
                free_names = node.free_type_level_names
                for name in free_names:
                    if name in names_to_defs:
                        ref_edges.append((def_id, names_to_defs[name]))
            graph = concat.graph.graph_from_edges(ref_edges)
            sccs = concat.graph.cycles(graph)
            for scc in sccs:
                kinds = []
                for def_id in scc:
                    kind: Kind = IndividualKind
                    type_parameters = self._get_class_params(
                        ids_to_defs[def_id], gamma
                    )[0]
                    if type_parameters:
                        kind = GenericTypeKind(
                            [v.kind for v in type_parameters], IndividualKind
                        )
                    kinds.append(kind)
                ty_vars = [ItemVariable(k) for k in kinds]
                fix_var = BoundVariable(TupleKind(kinds))
                gamma |= Environment(
                    {
                        ids_to_defs[def_id].class_name: ty_vars[i]
                        for i, def_id in enumerate(scc)
                    }
                )
                for i, def_id in enumerate(scc):

                    def fix_former(
                        env: Environment,
                        ty: Type,
                        # skipcq: PYL-W0102
                        ids_to_defs: dict[
                            int, concat.parse.ClassdefStatementNode
                        ] = ids_to_defs,
                        def_id: int = def_id,
                        scc: Sequence[int] = scc,
                        i: int = i,
                        fix_var: Variable = fix_var,
                    ) -> Type:
                        tys = [
                            env[ids_to_defs[def_id].class_name]
                            for def_id in scc
                        ]
                        tys[i] = ty
                        # I don't think reusing the fix_var is necessary since
                        # it won't be free in the other types, but I might as
                        # well since I've written that already.
                        return Fix(fix_var, TypeTuple(tys)).project(i)

                    gamma = gamma.with_mutuals(
                        ids_to_defs[def_id].class_name, fix_former
                    )
        finally:
            self._is_in_forward_references_phase = False

        for node in e:
            try:
                S, (i, o) = current_subs, current_effect

                if isinstance(node, concat.parse.PragmaNode):
                    namespace = 'concat.typecheck.'
                    if node.pragma.startswith(namespace):
                        pragma = node.pragma[len(namespace) :]
                    if pragma == 'builtin_object':
                        name = node.args[0]
                        self._object_type = gamma[name]
                        gamma[name].unsafe_set_type_id(Type.the_object_type_id)
                    if pragma == 'builtin_list':
                        name = node.args[0]
                        self._list_type = gamma[name]
                    if pragma == 'builtin_str':
                        name = node.args[0]
                        self._str_type = gamma[name]
                    if pragma == 'builtin_int':
                        name = node.args[0]
                        self._int_type = gamma[name]
                    if pragma == 'builtin_bool':
                        name = node.args[0]
                        self._bool_type = gamma[name]
                    if pragma == 'builtin_tuple':
                        name = node.args[0]
                        self._tuple_type = gamma[name]
                    if pragma == 'builtin_none':
                        name = node.args[0]
                        self._none_type = gamma[name]
                    if pragma == 'builtin_module':
                        name = node.args[0]
                        self._module_type = gamma[name]
                elif isinstance(node, concat.parse.PushWordNode):
                    S1, (i1, o1) = S, (i, o)
                    child = node.children[0]
                    if isinstance(child, concat.parse.FreezeWordNode):
                        should_instantiate = False
                        child = child.word
                    else:
                        should_instantiate = True
                    # special case for pushing an attribute accessor
                    if isinstance(child, concat.parse.AttributeWordNode):
                        top = o1[-1]
                        attr_type = top.get_type_of_attribute(child.value)
                        if should_instantiate:
                            attr_type = attr_type.instantiate()
                        rest_types = o1[:-1]
                        current_subs, current_effect = (
                            S1,
                            StackEffect(
                                i1, TypeSequence([*rest_types, attr_type])
                            ),
                        )
                    # special case for name words
                    elif isinstance(child, concat.parse.NameWordNode):
                        if child.value not in gamma:
                            raise NameError(child)
                        name_type = gamma[child.value]
                        # FIXME: Statically tell if a name is used before its
                        # definition is executed
                        if should_instantiate:
                            name_type = name_type.instantiate()
                        current_effect = StackEffect(
                            current_effect.input,
                            TypeSequence(
                                [
                                    *current_effect.output,
                                    current_subs(name_type),
                                ]
                            ),
                        )
                    elif isinstance(child, concat.parse.QuoteWordNode):
                        if child.input_stack_type is not None:
                            input_stack, _ = child.input_stack_type.to_type(
                                gamma
                            )
                        else:
                            # The majority of quotations I've written don't comsume
                            # anything on the stack, so make that the default.
                            input_stack = TypeSequence([SequenceVariable()])
                        S2, fun_type, _ = self.infer(
                            S1(gamma),
                            child.children,
                            extensions=extensions,
                            source_dir=source_dir,
                            initial_stack=input_stack,
                            check_bodies=check_bodies,
                        )
                        current_subs, current_effect = (
                            S2(S1),
                            StackEffect(
                                S2(i1),
                                TypeSequence(
                                    [*S2(o1), QuotationType(fun_type)]
                                ),
                            ),
                        )
                    else:
                        raise UnhandledNodeTypeError(
                            'quoted word {child} (repr {child!r})'.format(
                                child=child
                            )
                        )
                elif isinstance(node, concat.parse.ListWordNode):
                    phi = S
                    collected_type = o
                    element_type: 'Type' = no_return_type
                    for item in node.list_children:
                        phi1, fun_type, _ = self.infer(
                            phi(gamma),
                            item,
                            extensions=extensions,
                            source_dir=source_dir,
                            initial_stack=collected_type,
                            check_bodies=check_bodies,
                        )
                        collected_type = fun_type.output
                        # FIXME: Infer the type of elements in the list based on
                        # ALL the elements.
                        if element_type == no_return_type:
                            assert (
                                collected_type[-1].kind <= ItemKind
                            ), f'{collected_type} {collected_type[-1]}'
                            element_type = collected_type[-1]
                        # drop the top of the stack to use as the item
                        collected_type = collected_type[:-1]
                        phi = phi1(phi)
                    current_subs, current_effect = (
                        phi,
                        phi(
                            StackEffect(
                                i,
                                TypeSequence(
                                    [
                                        *collected_type,
                                        self._list_type[element_type,],
                                    ]
                                ),
                            )
                        ),
                    )
                elif isinstance(node, concat.parse.TupleWordNode):
                    phi = S
                    collected_type = current_effect.output
                    element_types: List[IndividualType] = []
                    for item in node.tuple_children:
                        phi1, fun_type, _ = self.infer(
                            phi(gamma),
                            item,
                            extensions=extensions,
                            source_dir=source_dir,
                            initial_stack=collected_type,
                            check_bodies=check_bodies,
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
                                TypeSequence(
                                    [
                                        *collected_type,
                                        self._tuple_type[element_types],
                                    ]
                                ),
                            )
                        ),
                    )
                elif isinstance(node, concat.parse.FromImportStatementNode):
                    imported_name = node.asname or node.imported_name
                    module_parts = node.value.split('.')
                    module_spec = None
                    path = None
                    if module_parts[0] in sys.builtin_module_names:
                        stub_path = pathlib.Path(__file__) / '../builtin_stubs'
                        for part in module_parts:
                            stub_path = stub_path / part
                    else:
                        for module_prefix in itertools.accumulate(
                            module_parts, lambda a, b: f'{a}.{b}'
                        ):
                            for finder in sys.meta_path:
                                module_spec = finder.find_spec(
                                    module_prefix, path
                                )
                                if module_spec is not None:
                                    path = (
                                        module_spec.submodule_search_locations
                                    )
                                    break
                        assert module_spec is not None
                        module_path = module_spec.origin
                        if module_path is None:
                            raise TypeError(
                                f'Cannot find path of module {node.value}',
                                is_occurs_check_fail=None,
                                rigid_variables=None,
                            )
                        # For now, assume the module's written in Python.
                        stub_path = pathlib.Path(module_path)
                    stub_path = stub_path.with_suffix('.cati')
                    stub_env = self._check_stub(
                        stub_path,
                        initial_env=self.load_builtins_and_preamble(),
                    )
                    imported_type = stub_env.get(node.imported_name)
                    if imported_type is None:
                        raise TypeError(
                            f'Cannot find {
                                node.imported_name
                            } in module {node.value}',
                            is_occurs_check_fail=None,
                            rigid_variables=None,
                        )
                    # TODO: Support star imports
                    gamma |= {imported_name: current_subs(imported_type)}
                elif isinstance(node, concat.parse.ImportStatementNode):
                    # TODO: Support all types of import correctly.
                    if node.asname is not None:
                        gamma |= {
                            node.asname: current_subs(
                                self._generate_type_of_innermost_module(
                                    node.value,
                                    source_dir=pathlib.Path(source_dir),
                                ).generalized_wrt(current_subs(gamma))
                            ),
                        }
                    else:
                        imported_name = node.value
                        # mutate type environment
                        components = node.value.split('.')
                        # FIXME: This replaces whatever was previously imported. I really
                        # should implement namespaces properly.
                        gamma |= {
                            components[0]: current_subs(
                                self._generate_module_type(
                                    components,
                                    source_dir=pathlib.Path(source_dir),
                                )
                            ),
                        }
                elif isinstance(node, concat.parse.FuncdefStatementNode):
                    S = current_subs
                    name = node.name
                    # NOTE: To continue the "bidirectional" bent, we will require a ghg
                    # type annotation.
                    # TODO: Make the return types optional?
                    declared_type, _ = node.stack_effect.to_type(S(gamma))
                    declared_type = S(declared_type)
                    if not isinstance(declared_type, StackEffect):
                        raise TypeError(
                            f'declared type of {name} must be a stack effect, got {declared_type}'
                        )
                    recursion_env = gamma | {
                        name: declared_type.generalized_wrt(S(gamma))
                    }
                    if check_bodies:
                        phi1, inferred_type, _ = self.infer(
                            S(recursion_env),
                            node.body,
                            is_top_level=False,
                            extensions=extensions,
                            initial_stack=declared_type.input,
                            check_bodies=check_bodies,
                        )
                        # We want to check that the inferred outputs are subtypes of
                        # the declared outputs. Thus, inferred_type.output should be a subtype
                        # declared_type.output.
                        rigid_variables = S(
                            recursion_env
                        ).free_type_variables()
                        try:
                            S = inferred_type.output.constrain_and_bind_variables(
                                self,
                                declared_type.output,
                                rigid_variables,
                                [],
                            )(S)
                        except TypeError as error:
                            message = (
                                'declared function type {} is not compatible with '
                                'inferred type {}'
                            )
                            raise TypeError(
                                message.format(declared_type, inferred_type),
                                is_occurs_check_fail=error.is_occurs_check_fail,
                                rigid_variables=rigid_variables,
                            ) from error
                    effect = declared_type
                    # type check decorators
                    _, final_type_stack, _ = self.infer(
                        gamma,
                        list(node.decorators),
                        is_top_level=False,
                        extensions=extensions,
                        initial_stack=TypeSequence([effect]),
                        check_bodies=check_bodies,
                    )
                    final_type_stack_output = (
                        final_type_stack.output.as_sequence()
                    )
                    if len(final_type_stack_output) != 1:
                        raise TypeError(
                            'Decorators produce too many stack items: only 1 '
                            f'should be left. Stack: {
                                final_type_stack.output
                            }',
                            is_occurs_check_fail=None,
                            rigid_variables=None,
                        )
                    final_type = final_type_stack_output[0]
                    if not (final_type.kind <= ItemKind):
                        raise TypeError(
                            format_decorator_result_kind_error(final_type),
                            is_occurs_check_fail=None,
                            rigid_variables=None,
                        )
                    gamma |= {
                        name: (
                            final_type.generalized_wrt(S(gamma))
                            if isinstance(final_type, StackEffect)
                            else final_type
                        ),
                    }
                elif isinstance(node, concat.parse.NumberWordNode):
                    if isinstance(node.value, int):
                        current_effect = StackEffect(
                            i, TypeSequence([*o, self._int_type])
                        )
                    else:
                        raise UnhandledNodeTypeError
                elif isinstance(node, concat.parse.NameWordNode):
                    (i1, o1) = current_effect
                    if node.value not in current_subs(gamma):
                        raise NameError(node)
                    type_of_name = current_subs(gamma)[node.value]
                    # FIXME: Statically tell if a name is used before its
                    # definition is executed
                    type_of_name = type_of_name.instantiate()
                    type_of_name = type_of_name.get_type_of_attribute(
                        '__call__'
                    ).instantiate()
                    out = SequenceVariable()
                    fun = StackEffect(o1, TypeSequence([out]))
                    constraint_subs = (
                        type_of_name.constrain_and_bind_variables(
                            self, fun, set(), []
                        )
                    )
                    current_subs = constraint_subs(current_subs)
                    current_effect = current_subs(StackEffect(i1, fun.output))
                elif isinstance(node, concat.parse.QuoteWordNode):
                    quotation = cast(concat.parse.QuoteWordNode, node)
                    # make sure any annotation matches the current stack
                    if quotation.input_stack_type is not None:
                        input_stack, _ = quotation.input_stack_type.to_type(
                            gamma
                        )
                        S = o.constrain_and_bind_variables(
                            self, input_stack, set(), []
                        )(S)
                    else:
                        input_stack = o
                    S1, (i1, o1), _ = self.infer(
                        gamma,
                        [*quotation.children],
                        extensions=extensions,
                        source_dir=source_dir,
                        initial_stack=input_stack,
                        check_bodies=check_bodies,
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
                            TypeSequence(
                                [*current_effect.output, self._str_type]
                            ),
                        ),
                    )
                elif isinstance(node, concat.parse.AttributeWordNode):
                    stack_top_type = o[-1]
                    out_types = o[:-1]
                    attr_function_type = stack_top_type.get_type_of_attribute(
                        node.value
                    ).instantiate()
                    attr_function_type_output = SequenceVariable()
                    R = attr_function_type.constrain_and_bind_variables(
                        self,
                        StackEffect(
                            out_types,
                            TypeSequence([attr_function_type_output]),
                        ),
                        set(),
                        [],
                    )
                    current_subs, current_effect = (
                        R(S),
                        R(StackEffect(i, attr_function_type_output)),
                    )
                elif isinstance(node, concat.parse.CastWordNode):
                    new_type, _ = node.type.to_type(gamma)
                    rest = current_effect.output[:-1]
                    current_effect = current_subs(
                        StackEffect(
                            current_effect.input,
                            TypeSequence([*rest, new_type]),
                        )
                    )
                elif isinstance(node, concat.parse.ParseError):
                    current_effect = StackEffect(
                        current_effect.input,
                        TypeSequence([SequenceVariable()]),
                    )
                elif not check_bodies and isinstance(
                    node, concat.parse.ClassdefStatementNode
                ):
                    gamma, sub = self._infer_class(
                        node, gamma, extensions, source_dir
                    )
                    current_subs = sub(current_subs)
                    gamma = current_subs(gamma)
                    current_effect = current_subs(current_effect)
                # TODO: Type aliases
                else:
                    raise UnhandledNodeTypeError(
                        "don't know how to handle '{}'".format(node)
                    )
            except TypeError as error:
                error.set_location_if_missing(node.location)
                raise
        return current_subs, current_effect, gamma

    @staticmethod
    def _get_class_params(
        node: concat.parse.ClassdefStatementNode, gamma: Environment
    ) -> Tuple[Sequence[Variable], Environment]:
        type_parameters: List[Variable] = []
        temp_gamma = gamma
        for param_node in node.type_parameters:
            if not isinstance(param_node, TypeNode):
                raise UnhandledNodeTypeError(param_node)
            param, temp_gamma = param_node.to_type(temp_gamma)
            type_parameters.append(param)
        if node.is_variadic:
            if len(type_parameters) > 1:
                raise TypeError(
                    format_too_many_params_for_variadic_type_error(),
                    is_occurs_check_fail=None,
                    rigid_variables=None,
                )
            underlying_kind = type_parameters[0].kind
            type_parameters = [
                BoundVariable(VariableArgumentKind(underlying_kind))
            ]
        return type_parameters, temp_gamma

    def _infer_class(
        self,
        node: concat.parse.ClassdefStatementNode,
        gamma: Environment,
        extensions: Sequence[Callable] | None,
        source_dir: str,
    ) -> tuple[Environment, Substitutions]:
        type_parameters, temp_gamma = self._get_class_params(node, gamma)
        assert not self._is_in_forward_references_phase
        _, _, body_attrs = self.infer(
            temp_gamma,
            node.body,
            extensions=extensions,
            source_dir=source_dir,
            initial_stack=TypeSequence([]),
            check_bodies=False,
        )
        # TODO: Introduce scopes into the environment object
        body_attrs = Environment(
            {
                name: ty
                for name, ty in body_attrs.items()
                if name not in temp_gamma
            }
        )
        ty: Type = ObjectType(
            attributes=body_attrs,
        )
        if type_parameters:
            ty = GenericType(
                type_parameters,
                ty,
            )
        ty = NominalType(Brand(node.class_name, ty.kind, []), ty)
        sub = Substitutions()
        if node.class_name in gamma:
            forward_ty = gamma[node.class_name]
            sub = ty.constrain_and_bind_variables(
                self,
                forward_ty,
                gamma.free_type_variables() - forward_ty.free_type_variables(),
                [],
            )
            fix_former = gamma.get_mutuals(node.class_name)
            ty = fix_former(gamma, ty)
        gamma |= Environment({node.class_name: ty})
        return gamma, sub

    _object_type: SetOnce[Type] = SetOnce()

    @property
    def object_type(self) -> Type:
        return self._object_type

    _module_type: SetOnce[Type] = SetOnce()

    @property
    def module_type(self) -> Type:
        return self._module_type

    _list_type: SetOnce[Type] = SetOnce()

    @property
    def list_type(self) -> Type:
        return self._list_type

    _str_type: SetOnce[Type] = SetOnce()

    @property
    def str_type(self) -> Type:
        return self._str_type

    _tuple_type: SetOnce[Type] = SetOnce()

    @property
    def tuple_type(self) -> Type:
        return self._tuple_type

    _int_type: SetOnce[Type] = SetOnce()

    @property
    def int_type(self) -> Type:
        return self._int_type

    _bool_type: SetOnce[Type] = SetOnce()
    _none_type: SetOnce[Type] = SetOnce()

    @property
    def none_type(self) -> Type:
        return self._none_type

    def check(
        self,
        environment: Environment,
        program: Sequence[concat.parse.Node],
        source_dir: str = '.',
        _should_check_bodies: bool = True,
    ) -> Environment:
        environment = Environment(
            {
                **concat.typecheck.preamble_types.types,
                **environment,
            }
        )
        res = self.infer(
            environment,
            program,
            None,
            True,
            source_dir,
            check_bodies=_should_check_bodies,
        )

        return res[2]

    def _generate_type_of_innermost_module(
        self, qualified_name: str, source_dir: pathlib.Path
    ) -> StackEffect:
        stub_path = _find_stub_path(qualified_name.split('.'), source_dir)
        init_env = self.load_builtins_and_preamble()
        module_attributes = self._check_stub(stub_path, init_env)
        module_type_brand = self._module_type.brand
        brand = Brand(
            f'type({qualified_name})', IndividualKind, [module_type_brand]
        )
        module_t = NominalType(brand, ObjectType(module_attributes))
        return StackEffect(
            TypeSequence([_seq_var]), TypeSequence([_seq_var, module_t])
        )

    def _generate_module_type(
        self,
        components: Sequence[str],
        _full_name: Optional[str] = None,
        source_dir='.',
    ) -> 'Type':
        if _full_name is None:
            _full_name = '.'.join(components)
        if len(components) > 1:
            module_type_brand = self._module_type.unroll().brand  # type: ignore
            brand = Brand(
                f'type({_full_name})', IndividualKind, [module_type_brand]
            )
            module_t = NominalType(
                brand,
                ObjectType(
                    {
                        components[1]: self._generate_module_type(
                            components[1:], _full_name, source_dir
                        )[_seq_var,],
                    }
                ),
            )
            effect = StackEffect(
                TypeSequence([_seq_var]), TypeSequence([_seq_var, module_t])
            )
            return GenericType([_seq_var], effect)
        innermost_type = self._generate_type_of_innermost_module(
            _full_name, source_dir=pathlib.Path(source_dir)
        )
        return GenericType([_seq_var], innermost_type)


def _find_stub_path(
    module_parts: Sequence[str], source_dir: pathlib.Path
) -> pathlib.Path:
    if module_parts[0] in sys.builtin_module_names:
        stub_path = pathlib.Path(__file__) / '../builtin_stubs'
        for part in module_parts:
            stub_path = stub_path / part
    else:
        module_spec = None
        path: Optional[List[str]]
        path = [str(source_dir)] + sys.path

        for module_prefix in itertools.accumulate(
            module_parts, lambda a, b: f'{a}.{b}'
        ):
            for finder in sys.meta_path:
                module_spec = finder.find_spec(module_prefix, path)
                if module_spec is not None:
                    path = module_spec.submodule_search_locations
                    break
        if module_spec is None:
            raise TypeError(
                format_cannot_find_module_from_source_dir_error(
                    '.'.join(module_parts),
                    source_dir,
                ),
                is_occurs_check_fail=None,
                rigid_variables=None,
            )
        module_path = module_spec.origin
        if module_path is None:
            raise TypeError(
                format_cannot_find_module_path_error('.'.join(module_parts)),
                is_occurs_check_fail=None,
                rigid_variables=None,
            )
        # For now, assume the module's written in Python.
        stub_path = pathlib.Path(module_path)
    stub_path = stub_path.with_suffix('.cati')
    return stub_path


# Parsing type annotations


class TypeNode(concat.parse.Node, abc.ABC):
    @abc.abstractmethod
    def to_type(self, env: Environment) -> Tuple['Type', Environment]:
        pass


class IndividualTypeNode(TypeNode, abc.ABC):
    pass


# A dataclass is not used here because making this a subclass of an abstract
# class does not work without overriding __init__ even when it's a dataclass.
class NamedTypeNode(TypeNode):
    def __init__(
        self,
        location: concat.astutils.Location,
        end_location: concat.astutils.Location,
        name: str,
    ) -> None:
        super().__init__(location, end_location, [])
        self.name = name
        self.children = []

    def __repr__(self) -> str:
        return '{}({!r}, {!r})'.format(
            type(self).__qualname__, self.location, self.name
        )

    def to_type(self, env: Environment) -> Tuple['Type', Environment]:
        type = env.get(self.name, None)
        if type is None:
            raise NameError(self.name, self.location)
        return type, env

    @property
    def free_type_level_names(self) -> set[str]:
        return {self.name}


class _GenericTypeNode(IndividualTypeNode):
    def __init__(
        self,
        location: concat.astutils.Location,
        end_location: concat.astutils.Location,
        generic_type: IndividualTypeNode,
        type_arguments: Sequence[IndividualTypeNode],
    ) -> None:
        super().__init__(
            location, end_location, [generic_type] + list(type_arguments)
        )
        self._generic_type = generic_type
        self._type_arguments = type_arguments
        self.end_location = end_location

    def to_type(self, env: Environment) -> Tuple[IndividualType, Environment]:
        args = []
        for arg in self._type_arguments:
            arg_as_type, env = arg.to_type(env)
            args.append(arg_as_type)
        generic_type, env = self._generic_type.to_type(env)
        if isinstance(generic_type.kind, GenericTypeKind):
            return generic_type[args], env
        raise TypeError(
            format_not_generic_type_error(generic_type),
            is_occurs_check_fail=None,
            rigid_variables=None,
        )


class _TypeSequenceIndividualTypeNode(IndividualTypeNode):
    def __init__(
        self,
        args: Tuple[concat.lex.Token, Optional[TypeNode]]
        | Tuple[Optional[concat.lex.Token], TypeNode],
    ) -> None:
        if args[0] is None:
            location = args[1].location
        else:
            location = args[0].start
        if args[1] is None:
            end_location = args[0].end
        else:
            end_location = args[1].end_location
        super().__init__(
            location,
            end_location,
            [n for n in args if isinstance(n, concat.parse.Node)],
        )
        self._name = None if args[0] is None else args[0].value
        self._type = args[1]

    # QUESTION: Should I have a separate space for the temporary associated
    # names?
    def to_type(self, env: Environment) -> Tuple[Type, Environment]:
        if self._type is not None:
            if self._name in env:
                assert self._name is not None
                raise TypeError(
                    format_name_reassigned_in_type_sequence_error(self._name),
                    is_occurs_check_fail=None,
                    rigid_variables=None,
                )
            ty, env = self._type.to_type(env)
            if self._name is not None:
                env |= {self._name: ty}
            return ty, env
        if self._name is not None:
            ty = env[self._name]
            if not (ty.kind <= ItemKind):
                raise TypeError(
                    format_item_type_expected_in_type_sequence_error(ty),
                    is_occurs_check_fail=None,
                    rigid_variables=None,
                )
            return ty, env
        assert False, 'there must be a name or a type'

    @property
    def name(self) -> Optional[str]:
        return self._name

    @property
    def type(self) -> Optional[TypeNode]:
        return self._type


class TypeSequenceNode(TypeNode):
    def __init__(
        self,
        location: concat.astutils.Location,
        end_location: concat.astutils.Location,
        seq_var: Optional['_SequenceVariableNode'],
        individual_type_items: Iterable[_TypeSequenceIndividualTypeNode],
    ) -> None:
        children: List[TypeNode] = [] if seq_var is None else [seq_var]
        children.extend(individual_type_items)
        super().__init__(location, end_location, children)
        self._sequence_variable = seq_var
        self._individual_type_items = tuple(individual_type_items)

    def to_type(self, env: Environment) -> Tuple[TypeSequence, Environment]:
        sequence: List[Type] = []
        temp_env = env
        if self._sequence_variable is None:
            # implicit stack polymorphism
            # FIXME: This should be handled in stack effect construction
            sequence.append(SequenceVariable())
        elif self._sequence_variable.name not in temp_env:
            var = SequenceVariable()
            temp_env |= {self._sequence_variable.name: var}
            sequence.append(var)
        for type_node in self._individual_type_items:
            type, temp_env = type_node.to_type(temp_env)
            sequence.append(type)
        return TypeSequence(sequence), env

    @property
    def sequence_variable(self) -> Optional['_SequenceVariableNode']:
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
        super().__init__(location, output.end_location, [input, output])
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
        new_env = env
        known_stack_item_names = Environment()
        if self.input_sequence_variable is not None:
            if self.input_sequence_variable.name in new_env:
                a_bar = cast(
                    SequenceVariable,
                    new_env[self.input_sequence_variable.name],
                )
            new_env |= {self.input_sequence_variable.name: a_bar}
        if self.output_sequence_variable is not None:
            if self.output_sequence_variable.name in new_env:
                b_bar = cast(
                    SequenceVariable,
                    new_env[self.output_sequence_variable.name],
                )
            else:
                b_bar = SequenceVariable()
                new_env |= {self.output_sequence_variable.name: b_bar}

        in_types = []
        for item in self.input:
            type, new_env, known_stack_item_names = _ensure_type(
                item[1],
                new_env,
                item[0],
                known_stack_item_names,
            )
            in_types.append(type)
        out_types = []
        for item in self.output:
            type, new_env, known_stack_item_names = _ensure_type(
                item[1],
                new_env,
                item[0],
                known_stack_item_names,
            )
            out_types.append(type)

        return (
            StackEffect(
                TypeSequence([a_bar, *in_types]),
                TypeSequence([b_bar, *out_types]),
            ),
            env,
        )


class _ItemVariableNode(TypeNode):
    """The AST type for item type variables."""

    def __init__(self, name: Token) -> None:
        super().__init__(name.start, name.end, [])
        self._name = name.value
        self.children = []

    def to_type(self, env: Environment) -> Tuple['Variable', Environment]:
        # QUESTION: Should callers be expected to have already introduced the
        # name into the context?
        if self._name in env:
            ty = env[self._name]
            if not (ty.kind <= ItemKind):
                error = TypeError(
                    format_expected_item_kinded_variable_error(
                        self._name,
                        ty,
                    ),
                    is_occurs_check_fail=None,
                    rigid_variables=None,
                )
                error.location = self.location
                raise error
            if not isinstance(ty, Variable):
                error = TypeError(
                    format_not_a_variable_error(self._name),
                    is_occurs_check_fail=None,
                    rigid_variables=None,
                )
                error.location = self.location
                raise error
            return ty, env

        var = BoundVariable(ItemKind)
        env |= {self._name: var}
        return var, env

    @property
    def name(self) -> str:
        return self._name


class _SequenceVariableNode(TypeNode):
    """The AST type for sequence type variables."""

    def __init__(self, name: Token) -> None:
        super().__init__(name.start, name.end, [])
        self._name = name.value
        self.children = []

    def to_type(
        self, env: Environment
    ) -> Tuple[SequenceVariable, Environment]:
        # QUESTION: Should callers be expected to have already introduced the
        # name into the context?
        if self._name in env:
            ty = env[self._name]
            if not isinstance(ty, SequenceVariable):
                error = TypeError(
                    f'{self._name} is not an sequence type variable',
                    is_occurs_check_fail=None,
                    rigid_variables=None,
                )
                error.location = self.location
                raise error
            return ty, env

        var = SequenceVariable()
        env |= {self._name: var}
        return var, env

    @property
    def name(self) -> str:
        return self._name


class _ForallTypeNode(TypeNode):
    """The AST type for universally quantified types."""

    def __init__(
        self,
        location: 'concat.astutils.Location',
        type_variables: Sequence[
            Union[_ItemVariableNode, _SequenceVariableNode]
        ],
        ty: TypeNode,
    ) -> None:
        children = list(type_variables) + [ty]
        super().__init__(location, ty.end_location, children)
        self._type_variables = type_variables
        self._type = ty

    def to_type(self, env: Environment) -> Tuple['Type', Environment]:
        temp_env = env
        variables = []
        for var in self._type_variables:
            parameter, temp_env = var.to_type(temp_env)
            variables.append(parameter)
        ty, _ = self._type.to_type(temp_env)
        forall_type = GenericType(variables, ty)
        return forall_type, env


class _ObjectTypeNode(IndividualTypeNode):
    """The AST type for anonymous structural object types."""

    def __init__(
        self,
        attribute_type_pairs: Iterable[Tuple[Token, IndividualTypeNode]],
        location: concat.astutils.Location,
        end_location: concat.astutils.Location,
    ) -> None:
        super().__init__(
            location, end_location, map(lambda p: p[1], attribute_type_pairs)
        )
        self._attribute_type_pairs = attribute_type_pairs

    def to_type(self, env: Environment) -> Tuple[ObjectType, Environment]:
        temp_env = env
        attribute_type_mapping: Dict[str, Type] = {}
        for attribute, type_node in self._attribute_type_pairs:
            ty, temp_env = type_node.to_type(temp_env)
            attribute_type_mapping[attribute.value] = ty
        # FIXME: Support recursive types in syntax
        return (
            ObjectType(
                attributes=attribute_type_mapping,
            ),
            env,
        )


def typecheck_extension(parsers: concat.parse.ParserDict) -> None:
    @concat.parser_combinators.generate
    def non_star_name_parser():
        name = yield concat.parse.token('NAME')
        if name.value == '*':
            yield concat.parser_combinators.fail('name that is not star (*)')
        return name

    @concat.parser_combinators.generate
    def named_type_parser():
        name_token = yield non_star_name_parser
        return NamedTypeNode(
            name_token.start, name_token.end, name_token.value
        )

    @concat.parser_combinators.generate
    def possibly_nullary_generic_type_parser() -> (
        Generator[
            concat.parser_combinators.Parser,
            Any,
            TypeNode,
        ]
    ):
        type_constructor_name = yield named_type_parser
        left_square_bracket: Token | None = yield concat.parse.token(
            'LSQB'
        ).optional()
        if left_square_bracket:
            type_arguments = yield parsers['type'].sep_by(
                concat.parse.token('COMMA'), min=1
            )
            end_location = (yield concat.parse.token('RSQB')).end
            return _GenericTypeNode(
                type_constructor_name.location,
                end_location,
                type_constructor_name,
                type_arguments,
            )
        return type_constructor_name

    @concat.parser_combinators.generate
    def individual_type_variable_parser():
        yield concat.parse.token('BACKTICK')
        name = yield non_star_name_parser

        return _ItemVariableNode(name)

    @concat.parser_combinators.generate
    def sequence_type_variable_parser():
        star = yield concat.parse.token('NAME')
        if star.value != '*':
            yield concat.parser_combinators.fail('star (*)')
        name = yield non_star_name_parser

        return _SequenceVariableNode(name)

    @concat.parser_combinators.generate
    def stack_effect_type_sequence_parser():
        type = parsers['type']

        # TODO: Allow type-only items
        item = concat.parser_combinators.seq(
            non_star_name_parser,
            (concat.parse.token('COLON') >> type).optional(),
        ).map(_TypeSequenceIndividualTypeNode)
        items = item.many()

        seq_var = sequence_type_variable_parser
        seq_var_parsed: Optional[_SequenceVariableNode]
        seq_var_parsed = yield seq_var.optional()
        i = yield items

        if seq_var_parsed is None and i:
            location = i[0].location
        elif seq_var_parsed is not None:
            location = seq_var_parsed.location
        else:
            prev_token = yield concat.parser_combinators.peek_prev.optional()
            if prev_token:
                location = prev_token.start
            else:
                location = (1, 0)

        if i:
            end_location = i[-1].end_location
        elif seq_var_parsed:
            end_location = seq_var_parsed.end_location
        else:
            end_location = location

        return TypeSequenceNode(location, end_location, seq_var_parsed, i)

    parsers['stack-effect-type-sequence'] = stack_effect_type_sequence_parser

    @concat.parser_combinators.generate
    def type_sequence_parser():
        type = parsers['type']

        item = type.map(lambda t: _TypeSequenceIndividualTypeNode((None, t)))
        items = item.many()

        seq_var = sequence_type_variable_parser
        seq_var_parsed: Optional[_SequenceVariableNode]
        seq_var_parsed = yield seq_var.optional()
        i = yield items

        if seq_var_parsed is None and i:
            location = i[0].location
        elif seq_var_parsed is not None:
            location = seq_var_parsed.location
        else:
            prev_token = yield concat.parser_combinators.peek_prev.optional()
            if prev_token:
                location = prev_token.start
            else:
                location = (1, 0)

        if i:
            end_location = i[-1].end_location
        elif seq_var_parsed:
            end_location = seq_var_parsed.end_location
        else:
            end_location = location

        return TypeSequenceNode(location, end_location, seq_var_parsed, i)

    @concat.parser_combinators.generate
    def stack_effect_type_parser():
        separator = concat.parse.token('MINUSMINUS')

        location = (yield concat.parse.token('LPAR')).start

        i = yield stack_effect_type_sequence_parser << separator
        o = yield stack_effect_type_sequence_parser

        yield concat.parse.token('RPAR')

        return StackEffectTypeNode(location, i, o)

    parsers['stack-effect-type'] = stack_effect_type_parser.desc(
        'stack effect type'
    )

    @concat.parser_combinators.generate
    def generic_type_parser():
        type = yield parsers['nonparameterized-type']
        yield concat.parse.token('LSQB')
        type_arguments = yield parsers['type'].sep_by(
            concat.parse.token('COMMA'), min=1
        )
        end_location = (yield concat.parse.token('RSQB')).end
        # TODO: Add end_location to all type nodes
        return _GenericTypeNode(
            type.location, end_location, type, type_arguments
        )

    @concat.parser_combinators.generate
    def forall_type_parser():
        forall = yield concat.parse.token('NAME')
        if forall.value != 'forall':
            yield concat.parser_combinators.fail('the word "forall"')

        type_variables = yield (
            individual_type_variable_parser | sequence_type_variable_parser
        ).at_least(1)

        yield concat.parse.token('DOT')

        ty = yield parsers['type']

        return _ForallTypeNode(forall.start, type_variables, ty)

    parsers['type-variable'] = concat.parser_combinators.alt(
        sequence_type_variable_parser,
        individual_type_variable_parser,
    )

    parsers['nonparameterized-type'] = concat.parser_combinators.alt(
        named_type_parser.desc('named type'),
        parsers.ref_parser('stack-effect-type'),
    )

    @concat.parser_combinators.generate
    def object_type_parser():
        location = (yield concat.parse.token('LBRACE')).start
        attribute_type_pair = concat.parser_combinators.seq(
            concat.parse.token('NAME') << concat.parse.token('COLON'),
            parsers['type'],
        )
        pairs = yield (attribute_type_pair.sep_by(concat.parse.token('COMMA')))
        end_location = (yield concat.parse.token('RBRACE')).end
        return _ObjectTypeNode(pairs, location, end_location)

    individual_type_parser = concat.parser_combinators.alt(
        possibly_nullary_generic_type_parser.desc(
            'named type or generic type',
        ),
        parsers.ref_parser('stack-effect-type'),
        object_type_parser.desc('object type'),
        individual_type_variable_parser,
    ).desc('individual type')

    parsers['type'] = concat.parser_combinators.alt(
        # NOTE: There's a parsing ambiguity that might come back to bite me...
        forall_type_parser.desc('forall type'),
        individual_type_parser,
        concat.parse.token('LPAR')
        >> parsers.ref_parser('type-sequence')
        << concat.parse.token('RPAR'),
        sequence_type_variable_parser,
    )

    parsers['type-sequence'] = type_sequence_parser.desc('type sequence')


_seq_var = SequenceVariable()


def _ensure_type(
    typename: Optional[TypeNode],
    env: Environment,
    obj_name: Optional[str],
    known_stack_item_names: Environment,
) -> Tuple['Type', Environment, Environment]:
    type: Type
    if obj_name and obj_name in known_stack_item_names:
        type = known_stack_item_names[obj_name]
    elif typename is None:
        type = ItemVariable(ItemKind)
    elif isinstance(typename, TypeNode):
        type, env = typename.to_type(env)
    else:
        raise NotImplementedError(
            'Cannot turn {!r} into a type'.format(typename)
        )
    if obj_name:
        known_stack_item_names |= {obj_name: type}
    return type, env, known_stack_item_names
