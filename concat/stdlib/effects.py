from typing import List, Generator, Callable, Type, Iterator, cast
import contextlib


_ConcatFunction = Callable[[List[object], List[object]], None]


class Effect:
    pass


class PureEffect(Effect):
    def __init__(self, x: object) -> None:
        self.value = x


class ContinuationEffect(Effect):
    def __init__(self, cont: _ConcatFunction) -> None:
        self.continuation = cont

    def run_effect(self, stack: List[object], stash: List[object]) -> None:
        self.continuation(stack, stash)
        if isinstance(stack[-1], ContinuationEffect):
            cast(ContinuationEffect, stack.pop()).run_effect(stack, stash)


class WriteEffect(Effect):
    def __init__(self, string: str) -> None:
        self.string = string


class ReadEffect(Effect):
    def __init__(self, prompt: str) -> None:
        self.prompt = prompt


_handler_stack = [
    (PureEffect, lambda s, t: s.append(s.pop().value)),
    (ContinuationEffect, lambda s, t: s.pop().continuation(s, t)),
]


# Effect Monad


class EffectMonad:
    @staticmethod
    def pure(x: object) -> 'PureEffect':
        return PureEffect(x)

    @staticmethod
    def bind(effect: 'Effect', f: _ConcatFunction) -> 'Effect':
        for effect_type, handler in _handler_stack[::-1]:
            if isinstance(effect, effect_type):

                @ContinuationEffect
                def cont(stack: List[object], stash: List[object]) -> None:
                    stack.append(effect)
                    handler(stack, stash)
                    f(stack, stash)

                return cont
        raise NotImplementedError(effect)

    @classmethod
    def do(cls, stack: List[object], stash: List[object]) -> None:
        # TODO: terminate
        cont = as_continuation(
            cast(Generator[object, object, object], stack.pop())
        )
        stack.append(cont)
        cls._do(stack, stash)

    @classmethod
    def _do(cls, stack: List[object], stash: List[object]) -> None:
        cont = cast(_ConcatFunction, stack.pop())
        cont(stack, stash)
        next, value = stack.pop(), stack.pop()
        if not isinstance(value, Effect):
            value = cls.pure(value)
        if next is None:
            stack.append(value)
            return

        def k(s: List[object], t: List[object]) -> None:
            s.append(None)
            s.append(next)
            cls._do(s, t)

        stack.append(cls.bind(value, k))


# Facility to capture the state of a generator as a continuation.


def as_continuation(
    generator: Generator[object, object, object]
) -> _ConcatFunction:
    """Returns a one-shot continuation that drives a generator."""
    # We could try making a multi-shot continuation like in
    # https://gist.github.com/yelouafi/858095244b62c36ec7ebb84d5f3e5b02, but I
    # don't want to make any assumptions about the statefulness and idempotency
    # of generators.
    def cont(stack: List[object], stash: List[object]) -> None:
        # TODO: Check that we are called only once.
        value = stack.pop()
        next = None
        try:
            yielded_value = generator.send(value)
        except StopIteration as e:
            yielded_value = e.value
        else:
            next = as_continuation(generator)
        stack.append(yielded_value)
        stack.append(next)

    return cont


@contextlib.contextmanager
def handle_effect(stack: List[object], stash: List[object]) -> Iterator:
    effect_type = cast(Type[Effect], stack.pop())
    handler = cast(_ConcatFunction, stack.pop())
    _handler_stack.append((effect_type, handler))
    yield
    _handler_stack.pop()


def effectful_computation(
    stack: List[object], stash: List[object]
) -> Generator[Effect, None, None]:
    yield ReadEffect("What's your name?")
    name = cast(str, stack.pop())
    yield WriteEffect('Hi, ' + name + '!')
    yield WriteEffect('Now go away!')


if __name__ == '__main__':
    stack: List[object] = [None]
    stash: List[object] = []
    stack.append(effectful_computation(stack, stash))
    stack += [
        lambda s, t: s.append(input(s.pop().prompt + '~~~> ')),
        ReadEffect,
    ]
    with handle_effect(stack, stash):
        stack += [lambda s, t: print(s.pop().string), WriteEffect]
        with handle_effect(stack, stash):
            EffectMonad.do(stack, stash)
            stack.pop().run_effect(stack, stash)
    print(stack)
