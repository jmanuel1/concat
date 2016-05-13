import builtins


class str(builtins.str):
    def join(self, stack):
        stack.append(super().join(stack.pop()))

    def index(self, stack):
        # print(stack)
        stack.append(super().index(stack.pop()))

    def format(self, stack):
        stack.append(super().format(*stack.pop()))
