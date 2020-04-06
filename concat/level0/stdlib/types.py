class Quotation(list):

    def __call__(self, stack, stash):
        for element in self:
            element(stack, stash)
