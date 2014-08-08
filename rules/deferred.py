import abc
import re
import six
from django.contrib.contenttypes.models import ContentType

__all__ = ['Selector', 'Function', 'DeferredValue', 'DeferredDict', 'DeferredList', 'ChainError']


@six.add_metaclass(abc.ABCMeta)
class DeferredValue(object):
    __slots__ = ()

    @abc.abstractmethod
    def maybe_const(self):  # pragma: no cover
        return self

    @abc.abstractmethod
    def _get_value(self, info):  # pragma: no cover
        raise NotImplementedError

    def get_value(self, info):
        try:
            return info[id(self)]
        except KeyError:
            result = info[id(self)] = self._get_value(info)
            return result

    def __ne__(self, other):
        x = self.__eq__(other)
        if x is NotImplemented:  # pragma: no cover
            return x
        return not x


class DeferredDict(dict, DeferredValue):
    __slots__ = ()

    def maybe_const(self):
        result = {}
        items = self.items() if six.PY3 else self.iteritems()
        for k, v in items:
            if isinstance(v, DeferredValue):
                v = v.maybe_const()
            # If there's even one deferred value left, this can't be a const.
            if isinstance(v, DeferredValue):
                return self
            result[k] = v
        return result

    def _get_value(self, info):
        items = self.items() if six.PY3 else self.iteritems()
        return {k: v.get_value(info) if isinstance(v, DeferredValue) else v for k, v in items}


class DeferredList(list, DeferredValue):
    __slots__ = ()

    def maybe_const(self):
        result = []
        for v in self:
            if isinstance(v, DeferredValue):
                v = v.maybe_const()
            # If there's even one deferred value left, this can't be a const.
            if isinstance(v, DeferredValue):
                return self
            result.append(v)
        return result

    def _get_value(self, info):
        return [x.get_value(info) if isinstance(x, DeferredValue) else x for x in self]


class ChainError(Exception):
    pass


class Selector(DeferredValue):
    __slots__ = ('stype', 'chain', 'first')

    def __init__(self, selector_type, chain):
        self.stype = selector_type
        self.chain = (chain.maybe_const() if isinstance(chain, DeferredValue) else chain) or ()
        if isinstance(selector_type, (list, tuple)):
            self.set_first(*selector_type)
        else:
            self.set_first(selector_type)

    def set_first(self, stype, arg=None):
        if isinstance(stype, DeferredValue):
            stype = stype.maybe_const()
            if isinstance(stype, DeferredValue):
                self.first = lambda info: stype.get_value(info)
            else:
                self.first = lambda info: stype
        elif isinstance(stype, int):
            self.first = lambda info: info['objects'][stype]
        elif stype == 'extra':
            self.first = lambda info: info['extra']
        elif stype == 'const':
            self.first = lambda info: arg
            self.stype = (stype, arg)
            if self.chain:
                raise ValueError('Chains are not allowed on "const" selectors')
        elif stype == 'model':
            try:
                m = ContentType.objects.get_by_natural_key(*arg.split('.')).model_class()
                m._meta
            except:
                raise ValueError('Invalid model for model selector: "{}"'.format(arg))
            self.first = lambda info: m
        else:
            raise NotImplementedError('Unknown selector type: "{}"'.format(stype))

    def maybe_const(self):
        if isinstance(self.stype, (list, tuple)):
            if self.stype[0] == 'const' or (self.stype[0] == 'model' and not self.chain):
                return self.first(None)
        elif isinstance(self.stype, DeferredValue) and not self.chain:
            return self.stype.maybe_const()
        return self

    def _get_value(self, info):
        obj = self.first(info)
        try:
            for getter in self.chain:
                if isinstance(getter, (list, tuple)):
                    getter, args = getter
                    if isinstance(args, DeferredValue):
                        args = args.get_value(info)
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

    def __eq__(self, other):
        try:
            return self is other or (self.stype == other.stype and self.chain == other.chain)
        except:
            if isinstance(other, DeferredValue):
                return False
            return NotImplemented  # pragma: no cover

    def __hash__(self):
        return hash((self.stype, tuple(self.chain)))


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

    __slots__ = ('func', 'name', 'args')

    def __init__(self, func, args):
        if func not in self.FUNCS:
            raise ValueError('"{}" is not a recognized function.'.format(func))
        self.func = self.FUNCS[func]
        self.name = func
        self.args = (args.maybe_const() if isinstance(args, DeferredValue) else args) or ()

    def maybe_const(self):
        if not isinstance(self.args, DeferredValue):
            return self.func(*self.args)
        return self

    def _get_value(self, info):
        args = self.args
        if isinstance(args, DeferredValue):
            args = args.get_value(info)
        return self.func(*args)

    def __eq__(self, other):
        try:
            return self is other or (self.func is other.func and self.args == other.args)
        except:
            if isinstance(other, DeferredValue):
                return False
            return NotImplemented  # pragma: no cover

    def __hash__(self):
        return hash((self.func, tuple(self.args)))
