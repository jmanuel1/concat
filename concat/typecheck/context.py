from __future__ import annotations
from contextlib import contextmanager
from contextvars import ContextVar
from typing import TYPE_CHECKING, Iterator


if TYPE_CHECKING:
    from concat.typecheck import TypeChecker


current_context: ContextVar[TypeChecker] = ContextVar('typechecker')


@contextmanager
def change_context(context: TypeChecker) -> Iterator[None]:
    token = current_context.set(context)
    yield
    current_context.reset(token)
