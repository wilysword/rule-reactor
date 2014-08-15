class Dummy(object):
    def __init__(self, ismatch, **kwargs):
        self.v = ismatch
        for k in kwargs:
            setattr(self, k, kwargs[k])

    def _match(self, info):
        if self.v:
            return self
        return False

    def negate(self):
        self.v = not self.v

    def _evaluate(self, info):
        return self.v

    def __str__(self):
        return str(id(self))
