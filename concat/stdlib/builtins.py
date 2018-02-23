import builtins
import concat.libconcat as libconcat


# not a subclass of builtins.str b/c the interface is so different
class str(libconcat.ConcatObject):

    # @libconcat.ConcatFunction
    def __init__(self, stack, stash):
        self._string = builtins.str(stack.pop())
        stack.append(self)

    def _pythonify_(self):
        return self._string

    @classmethod
    def _concatify_(cls, string):
        return cls([string], [])

    # @libconcat.ConcatFunction
    def join(self, stack, stash):
        # TODO: pythonify the sequence itself
        seq = [libconcat.pythonify(item) for item in stack.pop()]
        stack.append(type(self)._concatify_(self._string.join(seq)))

    # @libconcat.ConcatFunction
    def index(self, stack, stash):
        stack.append(libconcat.concatify(self._string.index(stack.pop())))

    # @libconcat.ConcatFunction
    def format(self, stack, stash):
        stack.append(type(self)._concatify_(self._string.format(*stack.pop())))

    def __str__(self):
        return self._string

    def __add__(self, other):
        return self._string + other

    def __iter__(self):
        return iter(self._string)

    def __getitem__(self, key):
        # print(key, type(key))
        return type(self)._concatify_(self._string[key])


libconcat.concatify.table[builtins.str] = str
