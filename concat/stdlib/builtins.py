import builtins
import concat.libconcat as libconcat


# not a subclass of builtins.str b/c the interface is so different
class str(libconcat.ConcatObject):

    # @libconcat.ConcatFunction
    def __init__(self, stack, stash):
        self._string = builtins.str(libconcat.pythonify(stack.pop()))
        stack.append(self)

    def _pythonify_(self):
        return self._string

    @classmethod
    def _concatify_(cls, string):
        return cls([string], [])

    # @libconcat.ConcatFunction
    def join(self, stack, stash):
        seq = libconcat.pythonify(stack.pop())
        stack.append(type(self)._concatify_(self._string.join(seq)))

    # @libconcat.ConcatFunction
    def index(self, stack, stash):
        substr = libconcat.pythonify(stack.pop())
        stack.append(libconcat.concatify(self._string.index(substr)))

    # @libconcat.ConcatFunction
    def format(self, stack, stash):
        args = libconcat.pythonify(stack.pop())
        stack.append(type(self)._concatify_(self._string.format(*args)))

    def __str__(self, stack, stash):
        """This function returns a Concat string."""
        stack.append(type(self)._concatify_(self._string))

    def __add__(self, stack, stash):
        other = libconcat.pythonify(stack.pop())
        stack.append(type(self)._concatify_(self._string + other))

    def __iter__(self, stack, stash):
        stack.append(libconcat.concatify(iter(self._string)))

    def __getitem__(self, stack, stash):
        # print(key, type(key))
        key = libconcat.pythonify(stack.pop())
        stack.append(type(self)._concatify_(self._string[key]))


class list(libconcat.ConcatObject):

    def __init__(self, stack, stash):
        self._list = builtins.list(libconcat.pythonify(stack.pop()))
        stack.append(self)

    def _pythonify_(self):
        return [libconcat.pythonify(obj) for obj in self._list]

    @classmethod
    def _concatify_(cls, obj):
        return cls([obj], [])


libconcat.concatify.table[builtins.str] = str
libconcat.concatify.table[builtins.list] = list
