import logging
from collections import defaultdict

logger = logging.getLogger(__name__)

__all__ = ['NoContinuationError', 'ContinuationStore', 'store', 'continuation']


class NoContinuationError(KeyError):
    pass


def noop(rule, info, value):
    logger.info('rule {} was matched, no continuation designated'.format(rule))


class ContinuationStore(defaultdict):
    def __missing__(self, key):
        if callable(key):
            return key
        elif key == 'noop' or not key:
            self[key] = noop
            return noop
        raise NoContinuationError(key)

    def register(self, *args, **kwargs):
        if not args:
            return lambda func: self.register(func, **kwargs)
        elif len(args) != 1 or not callable(args[0]):
            raise TypeError('Invalid positional argument to continuation')
        func = args[0]
        name = kwargs.get('name') or func.__name__
        if name in self or name == 'noop' or not name:
            raise ValueError('A continuation named "{}" already exists.'.format(name))
        self[name] = func
        return func

    def bind(self, context):
        bound = self.copy()
        for k in self:
            try:
                bind = self[k].bind
            except AttributeError:
                pass
            else:
                bound[k] = bind(context)
        return bound

    def unbind(self):
        for k in self:
            try:
                unbind = self[k].unbind
            except AttributeError:
                pass
            else:
                unbind()

store = ContinuationStore.default = ContinuationStore()

continuation = store.register
