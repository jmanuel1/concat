from typing import List


class Quotation(list):
    def __call__(self, stack: List[object], stash: List[object]) -> None:
        for element in self:
            element(stack, stash)
