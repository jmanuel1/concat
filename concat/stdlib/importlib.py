"""Helpers for importing modules."""


import types
from typing import List


class Module(types.ModuleType):
    def __call__(self, stack: List[object], _: List[object]) -> None:
        stack.append(self)
