import abc
import re
import six
from django.contrib.contenttypes.models import ContentType

__all__ = ['Selector', 'Function', 'DeferredValue', 'Deferred',
           'DeferredDict', 'DeferredList', 'ChainError']


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
            return info[id(self)]
        except KeyError:
            result = info[id(self)] = self._get_value(info)
            return result

    def get_value(self, info):
        value = self.maybe_const()
        if value is not self:
            self.get_value = lambda i: value
            return value
        self.get_value = self._get_deferred_value
        return self.get_value(info)


class DeferredDict(dict, Deferred):
    def maybe_const(self):
        result = {}
        for k, v in six.iteritems(self):
            vc = v
            if isinstance(v, Deferred):
                vc = v.maybe_const()
                if vc is v:
                    return self
            result[k] = vc
        return result

    def _get_value(self, info):
        return {k: v.get_value(info) if isinstance(v, Deferred) else v
                for k, v in six.iteritems(self)}


class DeferredList(list, Deferred):
    def maybe_const(self):
        result = []
        for v in self:
            vc = v
            if isinstance(v, Deferred):
                vc = v.maybe_const()
                if vc is v:
                    return self
            result.append(vc)
        return result

    def _get_value(self, info):
        return [x.get_value(info) if isinstance(x, Deferred) else x
                for x in self]


class DeferredValue(Deferred):
    def __ne__(self, other):
        return not self.__eq__(other)


class ChainError(Exception):
    pass


class Selector(DeferredValue):
    def __init__(self, selector_type, chain):
        self.chain = (chain if isinstance(chain, Deferred)
                      else DeferredList(chain or ()))
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
                val = self.stype.maybe_const()
                if val is not self.stype:
                    return val
        return self

    def _get_value(self, info):
        obj = self.first(info)
        try:
            for getter in self.chain.get_value(info):
                if isinstance(getter, list):
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
                     else DeferredList(args or ()))

    def __str__(self):
        return self.name + '(' + ', '.join(str(a) for a in self.args) + ')'

    def maybe_const(self):
        args = self.args.maybe_const()
        if args is self.args:
            return self
        return self.func(*args)

    def _get_value(self, info):
        return self.func(*self.args.get_value(info))

    def __eq__(self, obj):
        return self is obj or (self.func == getattr(obj, 'func', None) and
                               self.args == getattr(obj, 'args', None))
