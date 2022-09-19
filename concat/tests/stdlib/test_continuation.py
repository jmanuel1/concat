from concat.stdlib.continuation import ContinuationMonad
from hypothesis import given  # type: ignore
from hypothesis.strategies import integers  # type: ignore
from typing import Callable, TypeVar
import unittest


class TestContinuationMonad(unittest.TestCase):
    @given(integers())
    def test_functor_preserves_identity(self, i: int) -> None:
        cont = ContinuationMonad[int, int](lambda k: k(i))
        mapped_cont: ContinuationMonad[int, int] = cont.map(id)
        self.assertEqual(mapped_cont.run(id), cont.run(id))

    @given(integers(), integers(), integers())
    def test_functor_preserves_composition(
        self, i: int, j: int, l: int
    ) -> None:
        cont = ContinuationMonad[int, int](lambda k: k(i))
        f = lambda x: x + j
        g = lambda x: x + l
        composition_first_cont = cont.map(lambda x: f(g(x)))
        composition_last_cont = cont.map(g).map(f)
        self.assertEqual(
            composition_last_cont.run(id), composition_first_cont.run(id)
        )

    # https://en.wikibooks.org/wiki/Haskell/Applicative_functors

    @given(integers())
    def test_applicative_preserves_identity(self, i: int) -> None:
        cont = ContinuationMonad[int, int](lambda k: k(i))
        pure_id_applied_to_cont = (
            ContinuationMonad[int, Callable[[int], int]].pure(id).apply(cont)
        )
        self.assertEqual(pure_id_applied_to_cont.run(id), cont.run(id))

    @given(integers(), integers())
    def test_applicative_homomorphism_law(self, i: int, x: int) -> None:
        f = lambda x: x + i
        f_cont = ContinuationMonad[int, Callable[[int], int]].pure(f)
        x_cont = ContinuationMonad[int, int].pure(x)
        pure_f_appied_to_pure_x_cont = f_cont.apply(x_cont)
        pure_f_of_x_cont = ContinuationMonad[int, int].pure(f(x))
        self.assertEqual(
            pure_f_appied_to_pure_x_cont.run(id), pure_f_of_x_cont.run(id)
        )

    @given(integers(), integers())
    def test_applicative_interchange_law(self, i: int, y: int) -> None:
        u = lambda x: x + i
        u_cont = ContinuationMonad[int, Callable[[int], int]].pure(u)
        y_cont = ContinuationMonad[int, int].pure(y)
        u_applied_to_pure_y_cont = u_cont.apply(y_cont)
        pass_y_cont = ContinuationMonad[
            int, Callable[[Callable[[int], int]], int]
        ].pure(lambda f: f(y))
        pure_pass_y_applied_to_u_cont = pass_y_cont.apply(u_cont)
        self.assertEqual(
            u_applied_to_pure_y_cont.run(id),
            pure_pass_y_applied_to_u_cont.run(id),
        )

    @given(integers(), integers(), integers())
    def test_applicative_composition_law(self, i: int, j: int, w: int) -> None:
        compose_cont = ContinuationMonad[
            int,
            Callable[
                [Callable[[int], int]],
                Callable[[Callable[[int], int]], Callable[[int], int]],
            ],
        ].pure(lambda f: lambda g: lambda x: f(g(x)))
        u = lambda x: x + i
        u_cont = ContinuationMonad[int, Callable[[int], int]].pure(u)
        v = lambda x: x + j
        v_cont = ContinuationMonad[int, Callable[[int], int]].pure(v)
        w_cont = ContinuationMonad[int, int].pure(w)
        with_compose_cont = (
            compose_cont.apply(u_cont).apply(v_cont).apply(w_cont)
        )
        no_compose_cont = u_cont.apply(v_cont.apply(w_cont))
        self.assertEqual(with_compose_cont.run(id), no_compose_cont.run(id))

    # https://wiki.haskell.org/Monad_laws

    @given(integers(), integers())
    def test_monad_left_identity_law(self, a: int, j: int) -> None:
        a_cont = ContinuationMonad[int, int].pure(a)
        h = lambda x: ContinuationMonad[int, int].pure(x + j)
        return_a_bind_h_cont = a_cont.bind(h)
        h_of_a_cont = h(a)
        self.assertEqual(return_a_bind_h_cont.run(id), h_of_a_cont.run(id))

    @given(integers())
    def test_monad_right_identity_law(self, a: int) -> None:
        m_cont = ContinuationMonad[int, int].pure(a)
        return_cont = ContinuationMonad[int, int].pure
        m_bind_return_cont = m_cont.bind(return_cont)
        self.assertEqual(m_bind_return_cont.run(id), m_cont.run(id))

    @given(integers(), integers(), integers())
    def test_monad_associative_law(self, a: int, j: int, l: int) -> None:
        m_cont = ContinuationMonad[int, int].pure(a)
        g = lambda x: ContinuationMonad[int, int].pure(x + j)
        h = lambda x: ContinuationMonad[int, int].pure(x + l)
        m_bind_g_bind_h_cont = m_cont.bind(g).bind(h)
        m_bind_lambda_cont = m_cont.bind(lambda x: g(x).bind(h))
        self.assertEqual(
            m_bind_g_bind_h_cont.run(id), m_bind_lambda_cont.run(id)
        )

    @given(integers(), integers())
    def test_call_with_current_continuation(self, i: int, j: int) -> None:
        def pure_i(
            _: Callable[[int], ContinuationMonad[int, int]]
        ) -> ContinuationMonad[int, int]:
            return ContinuationMonad.pure(i)

        # don't use the continuation
        cont = ContinuationMonad[int, int].call_with_current_continuation(
            pure_i
        )
        self.assertEqual(cont.run(id), i)

        def aborted_mult(
            k: Callable[[int], ContinuationMonad[int, int]]
        ) -> ContinuationMonad[int, int]:
            return k(i).map(lambda x: x * j)

        # use the continuation
        cont = ContinuationMonad[int, int].call_with_current_continuation(
            aborted_mult
        )
        self.assertEqual(cont.run(id), i)


_T = TypeVar('_T')


def id(x: _T) -> _T:
    return x
