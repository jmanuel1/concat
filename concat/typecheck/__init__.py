"""The Concat type checker.

The type inference algorithm was originally based on the one described in
"Robert Kleffner: A Foundation for Typed Concatenative Languages, April 2017."
"""


from __future__ import annotations
from collections.abc import Generator
from concat.typecheck.errors import (
    NameError,
    StaticAnalysisError,
    TypeError,
    UnhandledNodeTypeError,
)
from typing import (
    Any,
    Callable,
    Dict,
    Iterable,
    Iterator,
    List,
    Mapping,
    Optional,
    Sequence,
    Set,
    TYPE_CHECKING,
    Tuple,
    TypeVar,
    Union,
    cast,
)
from typing_extensions import Protocol


if TYPE_CHECKING:
    import concat.astutils
    from concat.orderedset import InsertionOrderedSet
    from concat.typecheck.types import Type, Variable


class Environment(Dict[str, 'Type']):
    _next_id = -1

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.id = Environment._next_id
        Environment._next_id -= 1

    def copy(self) -> 'Environment':
        return Environment(super().copy())

    def apply_substitution(self, sub: 'Substitutions') -> 'Environment':
        return Environment({name: sub(t) for name, t in self.items()})

    def free_type_variables(self) -> 'InsertionOrderedSet[Variable]':
        return free_type_variables_of_mapping(self)


_Result = TypeVar('_Result', covariant=True)


class _Substitutable(Protocol[_Result]):
    def apply_substitution(self, sub: 'Substitutions') -> _Result:
        # empty, abstract protocol method
        pass


class Substitutions(Mapping['Variable', 'Type']):
    def __init__(
        self,
        sub: Union[
            Iterable[Tuple['Variable', 'Type']],
            Mapping['Variable', 'Type'],
            None,
        ] = None,
    ) -> None:
        self._sub = {} if sub is None else dict(sub)
        for variable, ty in self._sub.items():
            if not (variable.kind >= ty.kind):
                raise TypeError(
                    f'{variable} is being substituted by {ty}, which has the wrong kind ({variable.kind} vs {ty.kind})'
                )
        self._cache: Dict[int, 'Type'] = {}
        # innermost first
        self.subtyping_provenance: List[Any] = []

    def add_subtyping_provenance(
        self, subtyping_query: Tuple['Type', 'Type']
    ) -> None:
        self.subtyping_provenance.append(subtyping_query)

    def __getitem__(self, var: 'Variable') -> 'Type':
        return self._sub[var]

    def __iter__(self) -> Iterator['Variable']:
        return iter(self._sub)

    def __len__(self) -> int:
        return len(self._sub)

    def __bool__(self) -> bool:
        return bool(self._sub)

    def __call__(self, arg: _Substitutable[_Result]) -> _Result:
        from concat.typecheck.types import Type

        result: _Result
        # Previously I tried caching results by the id of the argument. But
        # since the id is the memory address of the object in CPython, another
        # object might have the same id later. I think this was leading to
        # nondeterministic Concat type errors from the type checker.
        if isinstance(arg, Type):
            if arg._type_id not in self._cache:
                if not (self._dom() & arg.free_type_variables()):
                    self._cache[arg._type_id] = arg
                else:
                    self._cache[arg._type_id] = arg.apply_substitution(self)
            result = self._cache[arg._type_id]
        if isinstance(arg, Environment):
            if arg.id not in self._cache:
                self._cache[arg.id] = arg.apply_substitution(self)
            result = self._cache[arg.id]
        result = arg.apply_substitution(self)
        return result

    def _dom(self) -> Set['Variable']:
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
        new_sub = Substitutions(
            {
                **sub,
                **{a: sub(i) for a, i in self.items() if a not in sub._dom()},
            }
        )
        new_sub.subtyping_provenance = [
            (self.subtyping_provenance, sub.subtyping_provenance)
        ]
        return new_sub

    def __hash__(self) -> int:
        return hash(tuple(self.items()))


from concat.typecheck.types import (
    BoundVariable,
    Brand,
    Fix,
    ForwardTypeReference,
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
    SequenceKind,
    SequenceVariable,
    StackEffect,
    StackItemType,
    TypeSequence,
    free_type_variables_of_mapping,
    get_int_type,
    get_list_type,
    get_str_type,
    get_tuple_type,
    get_module_type,
    no_return_type,
)
import abc
from concat.error_reporting import create_parsing_failure_message
from concat.lex import Token
import itertools
import pathlib
import sys
import concat.parser_combinators
import concat.parse


_builtins_stub_path = pathlib.Path(__file__) / '../builtin_stubs/builtins.cati'


def load_builtins_and_preamble() -> Environment:
    env = _check_stub(pathlib.Path(__file__).with_name('preamble0.cati'),)
    env = _check_stub(_builtins_stub_path, initial_env=env)
    env = _check_stub(
        pathlib.Path(__file__).with_name('preamble.cati'), initial_env=env,
    )
    # pick up ModuleType
    _check_stub(
        _builtins_stub_path.with_name('types.cati'), initial_env=env.copy(),
    )
    return env


def check(
    environment: Environment,
    program: 'concat.astutils.WordsOrStatements',
    source_dir: str = '.',
    _should_check_bodies: bool = True,
) -> Environment:
    import concat.typecheck.preamble_types

    environment = Environment(
        {**concat.typecheck.preamble_types.types, **environment,}
    )
    res = infer(
        environment,
        program,
        None,
        True,
        source_dir,
        check_bodies=_should_check_bodies,
    )

    return res[2]


# FIXME: I'm really passing around a bunch of state here. I could create an
# object to store it, or turn this algorithm into an object.
def infer(
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
    gamma = gamma.copy()
    for node in e:
        if isinstance(node, concat.parse.ClassdefStatementNode):
            type_name = node.class_name
            kind: Kind = IndividualKind
            type_parameters = []
            parameter_kinds: Sequence[Kind]
            if node.is_variadic:
                parameter_kinds = [SequenceKind]
            else:
                for param in node.type_parameters:
                    if isinstance(param, TypeNode):
                        type_parameters.append(param.to_type(gamma)[0])
                        continue
                    raise UnhandledNodeTypeError(param)
            if type_parameters:
                parameter_kinds = [
                    variable.kind for variable in type_parameters
                ]
                kind = GenericTypeKind(parameter_kinds, IndividualKind)
            gamma[type_name] = ForwardTypeReference(kind, type_name, gamma)

    for node in e:
        try:
            S, (i, o) = current_subs, current_effect

            if isinstance(node, concat.parse.PragmaNode):
                namespace = 'concat.typecheck.'
                if node.pragma.startswith(namespace):
                    pragma = node.pragma[len(namespace) :]
                if pragma == 'builtin_object':
                    name = node.args[0]
                    concat.typecheck.types.set_object_type(gamma[name])
                if pragma == 'builtin_list':
                    name = node.args[0]
                    concat.typecheck.types.set_list_type(gamma[name])
                if pragma == 'builtin_str':
                    name = node.args[0]
                    concat.typecheck.types.set_str_type(gamma[name])
                if pragma == 'builtin_int':
                    name = node.args[0]
                    concat.typecheck.types.set_int_type(gamma[name])
                if pragma == 'builtin_bool':
                    name = node.args[0]
                    concat.typecheck.types.set_bool_type(gamma[name])
                if pragma == 'builtin_tuple':
                    name = node.args[0]
                    concat.typecheck.types.set_tuple_type(gamma[name])
                if pragma == 'builtin_none':
                    name = node.args[0]
                    concat.typecheck.types.set_none_type(gamma[name])
                if pragma == 'builtin_module':
                    name = node.args[0]
                    concat.typecheck.types.set_module_type(gamma[name])
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
                    if isinstance(name_type, ForwardTypeReference):
                        raise NameError(child)
                    if should_instantiate:
                        name_type = name_type.instantiate()
                    current_effect = StackEffect(
                        current_effect.input,
                        TypeSequence(
                            [*current_effect.output, current_subs(name_type)]
                        ),
                    )
                elif isinstance(child, concat.parse.QuoteWordNode):
                    if child.input_stack_type is not None:
                        input_stack, _ = child.input_stack_type.to_type(gamma)
                    else:
                        # The majority of quotations I've written don't comsume
                        # anything on the stack, so make that the default.
                        input_stack = TypeSequence([SequenceVariable()])
                    S2, fun_type, _ = infer(
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
                            TypeSequence([*S2(o1), QuotationType(fun_type)]),
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
                    phi1, fun_type, _ = infer(
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
                        assert collected_type[-1] != SequenceKind
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
                                    get_list_type()[element_type,],
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
                    phi1, fun_type, _ = infer(
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
                                    get_tuple_type()[element_types],
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
                            module_spec = finder.find_spec(module_prefix, path)
                            if module_spec is not None:
                                path = module_spec.submodule_search_locations
                                break
                    assert module_spec is not None
                    module_path = module_spec.origin
                    if module_path is None:
                        raise TypeError(
                            f'Cannot find path of module {node.value}'
                        )
                    # For now, assume the module's written in Python.
                    stub_path = pathlib.Path(module_path)
                stub_path = stub_path.with_suffix('.cati')
                stub_env = _check_stub(
                    stub_path, initial_env=load_builtins_and_preamble()
                )
                imported_type = stub_env.get(node.imported_name)
                if imported_type is None:
                    raise TypeError(
                        f'Cannot find {node.imported_name} in module {node.value}'
                    )
                # TODO: Support star imports
                gamma[imported_name] = current_subs(imported_type)
            elif isinstance(node, concat.parse.ImportStatementNode):
                # TODO: Support all types of import correctly.
                if node.asname is not None:
                    gamma[node.asname] = current_subs(
                        _generate_type_of_innermost_module(
                            node.value, source_dir=pathlib.Path(source_dir)
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
                            components, source_dir=pathlib.Path(source_dir)
                        )
                    )
            elif isinstance(node, concat.parse.FuncdefStatementNode):
                S = current_subs
                name = node.name
                # NOTE: To continue the "bidirectional" bent, we will require a ghg
                # type annotation.
                # TODO: Make the return types optional?
                declared_type, _ = node.stack_effect.to_type(S(gamma))
                declared_type = S(declared_type)
                recursion_env = gamma.copy()
                if not isinstance(declared_type, StackEffect):
                    raise TypeError(
                        f'declared type of {name} must be a stack effect, got {declared_type}'
                    )
                recursion_env[name] = declared_type.generalized_wrt(S(gamma))
                if check_bodies:
                    phi1, inferred_type, _ = infer(
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
                    try:
                        S = inferred_type.output.constrain_and_bind_variables(
                            declared_type.output,
                            S(recursion_env).free_type_variables(),
                            [],
                        )(S)
                    except TypeError as e:
                        message = (
                            'declared function type {} is not compatible with '
                            'inferred type {}'
                        )
                        raise TypeError(
                            message.format(declared_type, inferred_type)
                        ) from e
                effect = declared_type
                # type check decorators
                _, final_type_stack, _ = infer(
                    gamma,
                    list(node.decorators),
                    is_top_level=False,
                    extensions=extensions,
                    initial_stack=TypeSequence([effect]),
                    check_bodies=check_bodies,
                )
                final_type_stack_output = final_type_stack.output.as_sequence()
                if len(final_type_stack_output) != 1:
                    raise TypeError(
                        f'Decorators produce too many stack items: only 1 should be left. Stack: {final_type_stack.output}'
                    )
                final_type = final_type_stack_output[0]
                if not isinstance(final_type, IndividualType):
                    raise TypeError(
                        f'Decorators should produce something of individual type, got {final_type}'
                    )
                # we *mutate* the type environment
                gamma[name] = (
                    final_type.generalized_wrt(S(gamma))
                    if isinstance(final_type, StackEffect)
                    else final_type
                )
            elif isinstance(node, concat.parse.NumberWordNode):
                if isinstance(node.value, int):
                    current_effect = StackEffect(
                        i, TypeSequence([*o, get_int_type()])
                    )
                else:
                    raise UnhandledNodeTypeError
            elif isinstance(node, concat.parse.NameWordNode):
                (i1, o1) = current_effect
                if node.value not in current_subs(gamma):
                    raise NameError(node)
                type_of_name = current_subs(gamma)[node.value]
                if isinstance(type_of_name, ForwardTypeReference):
                    raise NameError(node)
                type_of_name = type_of_name.instantiate()
                type_of_name = type_of_name.get_type_of_attribute(
                    '__call__'
                ).instantiate()
                if not isinstance(type_of_name, StackEffect):
                    raise UnhandledNodeTypeError(
                        'name {} of type {} (repr {!r})'.format(
                            node.value, type_of_name, type_of_name
                        )
                    )
                constraint_subs = o1.constrain_and_bind_variables(
                    type_of_name.input, set(), []
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
                    S = o.constrain_and_bind_variables(input_stack, set(), [])(
                        S
                    )
                else:
                    input_stack = o
                S1, (i1, o1), _ = infer(
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
                        TypeSequence([*current_effect.output, get_str_type()]),
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
                R = out_types.constrain_and_bind_variables(
                    attr_function_type.input, set(), []
                )
                current_subs, current_effect = (
                    R(S),
                    R(StackEffect(i, attr_function_type.output)),
                )
            elif isinstance(node, concat.parse.CastWordNode):
                new_type, _ = node.type.to_type(gamma)
                rest = current_effect.output[:-1]
                current_effect = current_subs(
                    StackEffect(
                        current_effect.input, TypeSequence([*rest, new_type])
                    )
                )
            elif isinstance(node, concat.parse.ParseError):
                current_effect = StackEffect(
                    current_effect.input, TypeSequence([SequenceVariable()]),
                )
            elif not check_bodies and isinstance(
                node, concat.parse.ClassdefStatementNode
            ):
                type_parameters: List[Variable] = []
                temp_gamma = gamma.copy()
                if node.is_variadic:
                    type_parameters.append(SequenceVariable())
                else:
                    for param_node in node.type_parameters:
                        if not isinstance(param_node, TypeNode):
                            raise UnhandledNodeTypeError(param_node)
                        param, temp_gamma = param_node.to_type(temp_gamma)
                        type_parameters.append(param)

                kind: Kind = IndividualKind
                if type_parameters:
                    kind = GenericTypeKind(
                        [v.kind for v in type_parameters], IndividualKind
                    )
                self_type = BoundVariable(kind)
                temp_gamma[node.class_name] = self_type
                _, _, body_attrs = infer(
                    temp_gamma,
                    node.body,
                    extensions=extensions,
                    source_dir=source_dir,
                    initial_stack=TypeSequence([]),
                    check_bodies=check_bodies,
                )
                # TODO: Introduce scopes into the environment object
                body_attrs = Environment(
                    {
                        name: ty
                        for name, ty in body_attrs.items()
                        if name not in temp_gamma
                    }
                )
                ty: Type = NominalType(
                    Brand(node.class_name, IndividualKind, []),
                    ObjectType(attributes=body_attrs,),
                )
                if type_parameters:
                    ty = GenericType(
                        type_parameters, ty, is_variadic=node.is_variadic
                    )
                ty = Fix(self_type, ty)
                gamma[node.class_name] = ty
            # TODO: Type aliases
            else:
                raise UnhandledNodeTypeError(
                    "don't know how to handle '{}'".format(node)
                )
        except TypeError as error:
            error.set_location_if_missing(node.location)
            raise
    return current_subs, current_effect, gamma


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
        if source_dir is not None:
            path = [str(source_dir)] + sys.path
        else:
            path = sys.path
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
                f'Cannot find module {".".join(module_parts)} from source dir {source_dir}'
            )
        module_path = module_spec.origin
        if module_path is None:
            raise TypeError(
                f'Cannot find path of module {".".join(module_parts)}'
            )
        # For now, assume the module's written in Python.
        stub_path = pathlib.Path(module_path)
    stub_path = stub_path.with_suffix('.cati')
    return stub_path


_module_namespaces: Dict[pathlib.Path, 'Environment'] = {}


def _check_stub_resolved_path(
    path: pathlib.Path, initial_env: Optional['Environment'] = None,
) -> 'Environment':
    if path in _module_namespaces:
        return _module_namespaces[path]
    try:
        source = path.read_text()
    except FileNotFoundError as e:
        raise TypeError(f'Type stubs at {path} do not exist') from e
    except IOError as e:
        raise TypeError(f'Failed to read type stubs at {path}') from e
    tokens = concat.lex.tokenize(source)
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
        _module_namespaces[path] = env
        return env
    recovered_parsing_failures = concat_ast.parsing_failures
    with path.open() as file:
        for failure in recovered_parsing_failures:
            print('Parse Error:')
            print(create_parsing_failure_message(file, tokens, failure))
    try:
        env = check(
            env,
            concat_ast.children,
            str(path.parent),
            _should_check_bodies=False,
        )
    except StaticAnalysisError as e:
        e.set_path_if_missing(path)
        raise
    _module_namespaces[path] = env
    return env


def _check_stub(
    path: pathlib.Path, initial_env: Optional['Environment'] = None,
) -> 'Environment':
    path = path.resolve()
    return _check_stub_resolved_path(path, initial_env)


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
        raise TypeError('{} is not a generic type'.format(generic_type))


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
                raise TypeError(
                    '{} is associated with a type more than once in this sequence of types'.format(
                        self._name
                    )
                )
            else:
                type, env = self._type.to_type(env)
                env = env.copy()
                if self._name is not None:
                    env[self._name] = type
                return type, env
        elif self._name is not None:
            ty = env[self._name]
            if not (ty.kind <= ItemKind):
                raise TypeError(
                    f'an item type was expected in this part of a type sequence, got {ty}'
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
        temp_env = env.copy()
        if self._sequence_variable is None:
            # implicit stack polymorphism
            # FIXME: This should be handled in stack effect construction
            sequence.append(SequenceVariable())
        elif self._sequence_variable.name not in temp_env:
            temp_env = temp_env.copy()
            var = SequenceVariable()
            temp_env[self._sequence_variable.name] = var
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
        new_env = env.copy()
        known_stack_item_names = Environment()
        if self.input_sequence_variable is not None:
            if self.input_sequence_variable.name in new_env:
                a_bar = cast(
                    SequenceVariable,
                    new_env[self.input_sequence_variable.name],
                )
            new_env[self.input_sequence_variable.name] = a_bar
        if self.output_sequence_variable is not None:
            if self.output_sequence_variable.name in new_env:
                b_bar = cast(
                    SequenceVariable,
                    new_env[self.output_sequence_variable.name],
                )
            else:
                b_bar = SequenceVariable()
                new_env[self.output_sequence_variable.name] = b_bar

        in_types = []
        for item in self.input:
            type, new_env = _ensure_type(
                item[1], new_env, item[0], known_stack_item_names,
            )
            in_types.append(type)
        out_types = []
        for item in self.output:
            type, new_env = _ensure_type(
                item[1], new_env, item[0], known_stack_item_names,
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
                    f'{self._name} is not an item type variable (has kind {ty.kind})'
                )
                error.location = self.location
                raise error
            return ty, env

        env = env.copy()
        var = BoundVariable(ItemKind)
        env[self._name] = var
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
                    f'{self._name} is not an sequence type variable'
                )
                error.location = self.location
                raise error
            return ty, env

        env = env.copy()
        var = SequenceVariable()
        env[self._name] = var
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
        temp_env = env.copy()
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
        temp_env = env.copy()
        attribute_type_mapping: Dict[str, IndividualType] = {}
        for attribute, type_node in self._attribute_type_pairs:
            ty, temp_env = type_node.to_type(temp_env)
            attribute_type_mapping[attribute.value] = ty
        # FIXME: Support recursive types in syntax
        return (
            ObjectType(attributes=attribute_type_mapping,),
            env,
        )


def typecheck_extension(parsers: concat.parse.ParserDict) -> None:
    @concat.parser_combinators.generate
    def non_star_name_parser() -> Generator:
        name = yield concat.parse.token('NAME')
        if name.value == '*':
            yield concat.parser_combinators.fail('name that is not star (*)')
        return name

    @concat.parser_combinators.generate
    def named_type_parser() -> Generator:
        name_token = yield non_star_name_parser
        return NamedTypeNode(
            name_token.start, name_token.end, name_token.value
        )

    @concat.parser_combinators.generate
    def possibly_nullary_generic_type_parser() -> Generator:
        type_constructor_name = yield named_type_parser
        left_square_bracket = yield concat.parse.token('LSQB').optional()
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
    def individual_type_variable_parser() -> Generator:
        yield concat.parse.token('BACKTICK')
        name = yield non_star_name_parser

        return _ItemVariableNode(name)

    @concat.parser_combinators.generate
    def sequence_type_variable_parser() -> Generator:
        star = yield concat.parse.token('NAME')
        if star.value != '*':
            yield concat.parser_combinators.fail('star (*)')
        name = yield non_star_name_parser

        return _SequenceVariableNode(name)

    @concat.parser_combinators.generate
    def stack_effect_type_sequence_parser() -> Generator:
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
    def type_sequence_parser() -> Generator:
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
    def stack_effect_type_parser() -> Generator:
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
    def generic_type_parser() -> Generator:
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
    def forall_type_parser() -> Generator:
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
        sequence_type_variable_parser, individual_type_variable_parser,
    )

    parsers['nonparameterized-type'] = concat.parser_combinators.alt(
        named_type_parser.desc('named type'),
        parsers.ref_parser('stack-effect-type'),
    )

    @concat.parser_combinators.generate
    def object_type_parser() -> Generator:
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


def _generate_type_of_innermost_module(
    qualified_name: str, source_dir: pathlib.Path
) -> StackEffect:
    stub_path = _find_stub_path(qualified_name.split('.'), source_dir)
    init_env = load_builtins_and_preamble()
    module_attributes = _check_stub(stub_path, init_env)
    module_type_brand = get_module_type().unroll().brand  # type: ignore
    brand = Brand(
        f'type({qualified_name})', IndividualKind, [module_type_brand]
    )
    module_t = NominalType(brand, ObjectType(module_attributes))
    return StackEffect(
        TypeSequence([_seq_var]), TypeSequence([_seq_var, module_t])
    )


def _generate_module_type(
    components: Sequence[str], _full_name: Optional[str] = None, source_dir='.'
) -> 'Type':
    if _full_name is None:
        _full_name = '.'.join(components)
    if len(components) > 1:
        module_type_brand = get_module_type().unroll().brand  # type: ignore
        brand = Brand(
            f'type({_full_name})', IndividualKind, [module_type_brand]
        )
        module_t = NominalType(
            brand,
            ObjectType(
                {
                    components[1]: _generate_module_type(
                        components[1:], _full_name, source_dir
                    )[_seq_var,],
                }
            ),
        )
        effect = StackEffect(
            TypeSequence([_seq_var]), TypeSequence([_seq_var, module_t])
        )
        return GenericType([_seq_var], effect)
    else:
        innermost_type = _generate_type_of_innermost_module(
            _full_name, source_dir=pathlib.Path(source_dir)
        )
        return GenericType([_seq_var], innermost_type)


def _ensure_type(
    typename: Optional[TypeNode],
    env: Environment,
    obj_name: Optional[str],
    known_stack_item_names: Environment,
) -> Tuple['Type', Environment]:
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
        known_stack_item_names[obj_name] = type
    return type, env
