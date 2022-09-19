from typing import Callable, Generic, Type, TypeVar


_A = TypeVar('_A', covariant=True)
_B = TypeVar('_B')
_C = TypeVar('_C')
_D = TypeVar('_D')
_R = TypeVar('_R')


class ContinuationMonad(Generic[_R, _A]):
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
