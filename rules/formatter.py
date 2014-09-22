from datetime import datetime, date, time
from decimal import Decimal
from json.encoder import encode_basestring_ascii
from six import string_types, iteritems

from .core import Condition, ConditionNode
from .deferred import DeferredValue, Selector, Function


def _format_dict(obj, deferred):
    pairs = (encode_basestring_ascii(k) + ':' + _format(v, deferred)
             for k, v in iteritems(obj))
    return '{' + ','.join(pairs) + '}'


def _format_list(obj, deferred):
    return '[' + ','.join(_format(v, deferred) for v in obj) + ']'


def _format_sel(obj, deferred):
    stype = obj.stype
    if isinstance(stype, int):
        stype = 'object:{}'.format(stype)
    elif isinstance(stype, DeferredValue):
        stype = _format_deferred(stype, deferred)
    elif stype == 'model':
        stype = 'model:' + obj.arg
    elif stype != 'extra':
        stype = 'const:' + _format(obj.arg, deferred)
    if obj.chain:
        chain = []
        for getter in obj.chain:
            if isinstance(getter, (list, tuple)):
                getter, arg = getter
                chain.append(str(getter) + ':' + _format(arg, deferred))
            else:
                chain.append(str(getter))
        return stype + '.' + ';.'.join(chain) + ';'
    return stype


def _format_func(obj, deferred):
    args = (_format(v, deferred) for v in obj.args)
    return obj.name + '(' + ','.join(args) + ')'


def _format_deferred(obj, deferred):
    try:
        index = deferred.index(obj) - 1
    except ValueError:
        if isinstance(obj, Selector):
            v = _format_sel(obj, deferred)
        elif isinstance(obj, Function):
            v = _format_func(obj, deferred)
        else:
            raise ValueError('Unknown deferred type')
        index = len(deferred[0])
        deferred[0].append(v)
        deferred.append(obj)
    return '\\' + str(index)


def _format_term(obj, deferred):
    if getattr(obj, 'stype', '') == 'const':
        return _format(obj.arg, None)
    return _format_deferred(obj, deferred)


def _format_cond(obj, deferred):
    left, op = _format_term(obj.left, deferred), obj.operator
    if obj.is_unary:
        cond = left + ' ' + op
    else:
        cond = left + ' ' + op + ' ' + _format_term(obj.right, deferred)
    return 'NOT ' + cond if obj.negated else cond


def _format_tree(obj, deferred):
    c = ' ' + obj.connector + ' '
    return '(' + c.join(_format(v, deferred) for v in obj.children) + ')'


def _format(obj, deferred):
    if obj is None:
        return 'null'
    elif obj is True:
        return 'true'
    elif obj is False:
        return 'false'
    elif isinstance(obj, (int, float, datetime, date, time, Decimal)):
        return str(obj)
    elif isinstance(obj, string_types):
        return encode_basestring_ascii(obj)
    elif isinstance(obj, dict):
        return _format_dict(obj, deferred)
    elif isinstance(obj, (list, tuple)):
        return _format_list(obj, deferred)
    elif isinstance(obj, DeferredValue):
        return _format_deferred(obj, deferred)
    elif isinstance(obj, Condition):
        return _format_cond(obj, deferred)
    elif isinstance(obj, ConditionNode):
        return _format_tree(obj, deferred)
    raise ValueError('Unknown object type')


def format_rule(obj):
    deferred = [[]]
    string = _format_tree(obj, deferred)
    if deferred:
        string = 'with(' + ','.join(deferred[0]) + ') ' + string
    return string
