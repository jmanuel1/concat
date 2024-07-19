from concat.common_types import ConcatFunction
from typing import Any, Callable, Generic, List, NoReturn, Type, TypeVar, cast


_A = TypeVar('_A', covariant=True)
_B = TypeVar('_B')
_C = TypeVar('_C')
_D = TypeVar('_D')
_R = TypeVar('_R')


class ContinuationMonad(Generic[_R, _A]):
    """The continuation monad, implemented as a Python class.

    The Concat interface to this type is defined separately.
    """

    def __init__(self, run: Callable[[Callable[[_A], _R]], _R]) -> None:
        self._run = run

    def run(self, continuation: Callable[[_A], _R]) -> _R:
        return self._run(continuation)

    def map(self, f: Callable[[_A], _B]) -> 'ContinuationMonad[_R, _B]':
        # https://blog.poisson.chat/posts/2019-10-26-reasonable-continuations.html
        m = self._run
        # I use a composition combinator instead of an explicit lambda here
        # because of https://github.com/python/mypy/issues/8191.
        return ContinuationMonad(lambda k: m(compose(k, f)))

    @classmethod
    def pure(
        cls: Type['ContinuationMonad[_R, _C]'], value: _C
    ) -> 'ContinuationMonad[_R, _C]':
        return cls(lambda k: k(value))

    def apply(
        self: 'ContinuationMonad[_R, Callable[[_B], _C]]',
        argument: 'ContinuationMonad[_R, _B]',
    ) -> 'ContinuationMonad[_R, _C]':
        return ContinuationMonad(
            lambda k: self._run(lambda f: argument._run(lambda a: k(f(a))))
        )

    def bind(
        self, f: Callable[[_A], 'ContinuationMonad[_R, _B]']
    ) -> 'ContinuationMonad[_R, _B]':
        return ContinuationMonad(
            lambda k: self._run(
                compose(lambda cont: self._run_bound_continuation(cont, k), f)
            )
        )

    @staticmethod
    def _run_bound_continuation(
        continuation: 'ContinuationMonad[_R, _B]', k: Callable[[_B], _R]
    ) -> _R:
        return continuation._run(k)

    @classmethod
    def call_with_current_continuation(
        cls: Type['ContinuationMonad[_R, _B]'],
        f: Callable[
            [Callable[[_B], 'ContinuationMonad[_R, _C]']],
            'ContinuationMonad[_R, _B]',
        ],
    ) -> 'ContinuationMonad[_R, _B]':
        # https://hackage.haskell.org/package/transformers-0.6.0.4/docs/src/Control.Monad.Trans.Cont.html#callCC
        return cls(
            lambda k: f(
                lambda b: ContinuationMonad[_R, _C](lambda _: k(b))
            )._run(k)
        )


def compose(
    f: Callable[[_B], _R], g: Callable[[_C], _B]
) -> Callable[[_C], _R]:
    return lambda c: f(g(c))


# Concat API


def call_with_current_continuation(
    stack: List[object], stash: List[object]
) -> None:
    """$f -- (call/cc $f)"""
    f = cast(Callable[[List[object], List[object]], None], stack.pop())

    def python_function(
        k: Callable[[_B], ContinuationMonad[_R, _C]]
    ) -> ContinuationMonad[_R, _B]:
        def concat_function(stack: List[object], _: List[object]) -> None:
            stack.append(k(cast(_B, stack.pop())))

        # I think using the same stacks is safe because the type of `f` should
        # promise it doesn't look beyond `k` in the stack.
        stack.append(concat_function)
        f(stack, stash)
        return cast(ContinuationMonad[_R, _B], stack.pop())

    stack.append(
        ContinuationMonad.call_with_current_continuation(python_function)
    )


def eval_cont(stack: List[object], _: List[object]) -> None:
    cont = cast(ContinuationMonad, stack.pop())
    result = cont._run(lambda x: x)
    stack.append(result)


def cont_pure(stack: List[object], _: List[object]) -> None:
    value = stack.pop()
    result = ContinuationMonad[NoReturn, object].pure(value)
    stack.append(result)


def map_cont(stack: List[Any], stash: List[Any]) -> None:
    f, cont = (
        cast(ConcatFunction, stack.pop()),
        cast(ContinuationMonad, stack.pop()),
    )

    def python_function(b: Any) -> Any:
        stack.append(b)
        f(stack, stash)
        return stack.pop()

    result = cont.map(python_function)
    stack.append(result)


def bind_cont(stack: List[object], stash: List[object]) -> None:
    f, cont = (
        cast(ConcatFunction, stack.pop()),
        cast(ContinuationMonad, stack.pop()),
    )

    def python_function(b: _B) -> ContinuationMonad[_R, _C]:
        # rely on stack polymorphism of f
        stack.append(b)
        f(stack, stash)
        return cast(ContinuationMonad[_R, _C], stack.pop())

    result: ContinuationMonad = cont.bind(python_function)
    stack.append(result)


def cont_from_cps(stack: List[object], stash: List[object]) -> None:
    concat_run = cast(ConcatFunction, stack.pop())

    def python_run(python_k: Callable[[_B], _R]) -> _R:
        def concat_k(stack: List[object], _: List[object]) -> None:
            b = cast(_B, stack.pop())
            stack.append(python_k(b))

        # rely on stack polymorphism of concat_run
        stack.append(concat_k)
        concat_run(stack, stash)
        return cast(_R, stack.pop())

    result: ContinuationMonad = ContinuationMonad(python_run)
    stack.append(result)
