"""Based on https://docs.factorcode.org/content/article-continuations.html."""

from typing import List, Callable, Iterator, Optional, cast
import contextlib


class _ContinuationException(Exception):
    def __init__(self, id: int) -> None:
        self.continuation_id = id


class _Continuation:
    pass


_return_continuation: Optional[_Continuation] = None


def callcc(stack: List[object], stash: List[object]) -> None:
    """*s (*s continuation:(*t -- *u) -- *t) -- *t"""
    func = cast(Callable[[List[object], List[object]], None], stack.pop())
    continuation = _Continuation()
    stack.append(continuation)
    try:
        func(stack, stash)
    except _ContinuationException as e:
        if e.continuation_id != id(continuation):
            raise


def continue_with(stack: List[object], stash: List[object]) -> None:
    """*s continuation:(*s -- *t) -- `unreachable until just after matching callcc`"""
    # Since we use exceptions, and continuations are unbounded, they are
    # single-shot and don't return.
    continuation = stack.pop()
    raise _ContinuationException(id(continuation))


@contextlib.contextmanager
def _set_return_continuation(continuation: _Continuation) -> Iterator[None]:
    global _return_continuation
    previous_continuation = _return_continuation
    _return_continuation = continuation
    yield
    _return_continuation = previous_continuation


def do_return(stack: List[object], stash: List[object]) -> None:
    """ -- `unreachable until just after matching with_return`"""
    stack.append(_return_continuation)
    continue_with(stack, stash)


def _with_return_inner(stack: List[object], stash: List[object]) -> None:
    with _set_return_continuation(cast(_Continuation, stack.pop())):
        cast(Callable[[List[object], List[object]], None], stack.pop())(
            stack, stash
        )


def with_return(stack: List[object], stash: List[object]) -> None:
    """*s (*s -- *t) -- *t"""
    stack.append(_with_return_inner)
    callcc(stack, stash)
