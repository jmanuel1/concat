import random as r
import concat.libconcat as libconcat


@libconcat.ConcatFunction
def random(stack, stash):
    stack.append(libconcat.concatify(r.random()))
