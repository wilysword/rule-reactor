import abc
import re
import six
from django.contrib.contenttypes.models import ContentType

__all__ = ['Selector', 'Function', 'DeferredValue', 'Deferred',
           'DeferredDict', 'DeferredTuple', 'ChainError', 'StillDeferred']


class StillDeferred(Exception):
    pass


@six.add_metaclass(abc.ABCMeta)
class Deferred(object):
    @abc.abstractmethod
    def maybe_const(self):  # pragma: no cover
        return self

    @abc.abstractmethod
    def _get_value(self, info):  # pragma: no cover
        raise NotImplementedError

    def _get_deferred_value(self, info):
        try:
            return info[self]
        except KeyError:
            result = info[self] = self._get_value(info)
            return result

    def get_value(self, info):
        try:
            value = self.maybe_const()
            self.get_value = lambda i: value
        except StillDeferred:
            self.get_value = self._get_deferred_value
        return self.get_value(info)


def _make_hashable(obj):
    if isinstance(obj, dict):
        return tuple((k, _make_hashable(v)) for k, v in six.iteritems(obj))
    elif isinstance(obj, (list, tuple)):
        return tuple(_make_hashable(v) for v in obj)
    return obj


def _make_hashwrapper(get_hashable):
    def __hash__(self):
        try:
            h = self._hash
        except AttributeError:
            h = self._hash = hash(get_hashable(self))
        return h
    return __hash__


class DeferredDict(dict, Deferred):
    def maybe_const(self):
        return {k: v.maybe_const() if isinstance(v, Deferred) else v
                for k, v in six.iteritems(self)}

    def _get_value(self, info):
        return {k: v.get_value(info) if isinstance(v, Deferred) else v
                for k, v in six.iteritems(self)}

    __hash__ = _make_hashwrapper(_make_hashable)
    __setitem__ = __delitem__ = NotImplemented
    pop = popitem = clear = update = setdefault = NotImplemented


class DeferredTuple(tuple, Deferred):
    def maybe_const(self):
        return tuple(x.maybe_const() if isinstance(x, Deferred) else x
                     for x in self)

    def _get_value(self, info):
        return tuple(x.get_value(info) if isinstance(x, Deferred) else x
                     for x in self)

    __hash__ = _make_hashwrapper(_make_hashable)


class DeferredValue(Deferred):
    def __ne__(self, other):
        return not self.__eq__(other)


class ChainError(Exception):
    pass


class Selector(DeferredValue):
    def __init__(self, selector_type, chain):
        self.chain = (chain if isinstance(chain, Deferred)
                      else DeferredTuple(chain or ()))
        if isinstance(selector_type, (list, tuple)):
            self.set_first(*selector_type)
        else:
            self.set_first(selector_type)

    def set_first(self, stype, arg=None):
        self.stype, self.arg = stype, arg
        if isinstance(stype, DeferredValue):
            self.first = stype.get_value
        elif isinstance(stype, int):
            self.first = lambda info: info['objects'][stype]
        elif stype == 'extra':
            self.first = lambda info: info['extra']
        elif stype == 'const':
            self.first = lambda info: arg
            assert not self.chain
        elif stype == 'model':
            m = arg.split('.')
            m = ContentType.objects.get_by_natural_key(*m).model_class()
            self.first = lambda info: m
        else:
            raise NotImplementedError('Unknown selector type: "{}"'
                                      .format(stype))

    def __str__(self):
        stype = self.stype
        if stype in ('const', 'model'):
            stype = '{}:{}'.format(stype, self.arg)
        if self.chain:
            return '{}.{}'.format(stype, '.'.join(str(y) for y in self.chain))
        return str(stype)

    def maybe_const(self):
        if not self.chain:
            if self.stype in ('const', 'model'):
                return self.first(None)
            elif isinstance(self.stype, DeferredValue):
                return self.stype.maybe_const()
        raise StillDeferred(self)

    def _get_value(self, info):
        obj = self.first(info)
        try:
            for getter in self.chain.get_value(info):
                if isinstance(getter, tuple):
                    getter, args = getter
                else:
                    args = ()
                try:
                    obj = obj[getter]
                except (KeyError, TypeError):
                    obj = getattr(obj, getter)
                if callable(obj):
                    if isinstance(args, dict):
                        obj = obj(**args)
                    elif isinstance(args, (list, tuple)):
                        obj = obj(*args)
                    else:
                        obj = obj(args)
        except ChainError:  # pragma: no cover
            raise
        except Exception as ex:
            raise ChainError(ex)
        return obj

    def __eq__(self, obj):
        return self is obj or (self.stype == getattr(obj, 'stype', None) and
                               self.arg == getattr(obj, 'arg', None) and
                               self.chain == getattr(obj, 'chain', None))

    __hash__ = lambda s: (s.stype, _make_hashable(s.arg), s.chain)
    __hash__ = _make_hashwrapper(__hash__)


class Function(DeferredValue):
    FUNCS = {
        'len': len,
        'list': list,
        'dict': dict,
        'tuple': tuple,
        'set': set,
        'percent': (lambda x, y: 100. * x / y),
        'max': max,
        'min': min,
        'str': str,
        'sum': sum,
        'int': int,
        'float': float,
        'hex': hex,
        'abs': abs,
        'round': round,
        'regex': re.compile
    }

    def __init__(self, func, args):
        self.func = self.FUNCS[func]
        self.name = func
        self.args = (args if isinstance(args, Deferred)
                     else DeferredTuple(args or ()))

    def __str__(self):
        return self.name + '(' + ', '.join(str(a) for a in self.args) + ')'

    def maybe_const(self):
        return self.func(*self.args.maybe_const())

    def _get_value(self, info):
        return self.func(*self.args.get_value(info))

    def __eq__(self, obj):
        return self is obj or (self.name == getattr(obj, 'name', None) and
                               self.args == getattr(obj, 'args', None))

    __hash__ = _make_hashwrapper(lambda s: (s.name, s.args))
