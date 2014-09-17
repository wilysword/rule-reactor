r"""
Parses strings into rules according to the following syntax:

<rule> ::= <withlist> <ws> <tree> | <tree>

<tree> ::= <condition> | "NOT" <ws> <tree> | "(" <tree> ")" |
           <tree> <connector> <tree>

<connector> ::= <ws> "AND" <ws> | <ws> "OR" <ws>

<condition> ::= <value> <ws> <uop> | <value> <ws> <bop> <ws> <value>

<uop> ::= "exists" | "does not exist" | "bool"

<bop> ::= "==" | "!=" | "<" | "<=" | ">" | ">=" | "in" | "not in" |
          "like" | "re" | "not like"

<deferred> ::= <selector> | <function>

<withlist> ::= "with(" <optws> <deferredlist> <optws> ")"

<deferredlist> ::= <deferred> | <deferred> <optws> "," <optws> <deferredlist>

<selector> ::= "const:" <value> | <stype> <chain>

<stype> ::= "extra" | "object:" <integer> | "\" <integer> |
            "model:" <symbol> "." <symbol>

<chain> ::= <chainident> | <chainident> ":" <value> | <chain> <chain>

<chainident> ::= "." <integer> | "." <symbol>

<function> ::= <funcname> "(" <optws> <valuelist> <optws> ")" |
               <funcname> "(" <optws> ")"

<funcname> ::= "len" | "list" | "dict" | "tuple" | "set" | "percent" |
               "max" | "min" | "str" | "sum" | "int" | "float" | "hex" |
               "abs" | "round" | "regex"

<valuelist> ::= <value> | <value> <optws> "," <optws> <valuelist>

<value> ::= <deferred> | <dict> | <list> | <date> | <time> | <datetime> |
            "null" | <number> | <bool> | <string>

<list> ::= "[" <optws> "]" | "[" <optws> <valuelist> <optws> "]"

<dict> ::= "{" <optws> "}" | "{" <optws> <pairlist> <optws> "}"

<pairlist> ::= <pair> | <pair> <optws> "," <optws> <pairlist>

<pair> ::= <string> <optws> ":" <optws> <value>

<optws> ::= "" | <ws>

Other:
  * <date>, <time>, and <datetime> formats are what would result from calling
    :func:`str` on correspondingly named Python objects (i.e. ISO formats).
  * <string>, <number>, <integer>, and <bool> all follow the expected rules
    used by Python's :mod:`json` module.
  * <ws> is one or more whitespace characters, such as would be matched in a
    regex by ``\s`` or would cause :meth:`str.isspace` to return ``True``.
  * <symbol> is any valid Python identifier, as using the regex ``[^\d\W]\w*``
"""
import re
from collections import defaultdict
from json.decoder import scanstring
from madlibs.parser import Parser, subparser, parseloop, with_parsers
from madlibs.json import parse_date, parse_time, parse_datetime
from .core import *
from .deferred import *

__all__ = ['RuleParser', 'parse_rule']


class _floatdict(defaultdict):
    def __missing__(self, key):
        v = float(key)
        self[key] = v
        return v
_FLOATS = _floatdict()


def parse_number(pinfo, string, index):
    m = _nummatch(string, index)
    if m:
        whole, frac, exp = m.groups()
        if frac or exp:
            return float(whole + (frac or '') + (exp or '')), m.end()
        else:
            return int(whole), m.end()
    m = _floatconstmatch(string, index)
    if m:
        val = m.group()
        return _FLOATS[val], m.end()
    return NotImplemented, index
_nummatch = re.compile(r'(-?[1-9][0-9]*|0)(\.[0-9]*)?([eE][+-]?[0-9]+)?').match
_floatconstmatch = re.compile('[-+]?inf(?:inity)?|nan', flags=re.I).match


def parse_const(pinfo, string, index):
    i4 = index + 4
    if string[index:i4] == 'true':
        return True, i4
    elif string[index:i4 + 1] == 'false':
        return False, i4 + 1
    elif string[index:i4] == 'null':
        return None, i4
    return NotImplemented, index


def parse_string(pinfo, string, index):
    if index < len(string) and string[index] == '"':
        return scanstring(string, index + 1)
    return NotImplemented, index


def _error(index, msg='Invalid Rule starting at index {}'):
    return ValueError(msg.format(index))


def _parse_list(pinfo, string, index, parse=None,
                expect=False, term=')', obj=None):
    if parse is None:
        parse = pinfo['parse']
    if obj is None:
        obj = DeferredList()
    length = len(string)
    while index < length:
        c = string[index]
        if c.isspace():
            index += 1
            continue
        if expect:
            result, index = parse(pinfo, string, index)
            if result is NotImplemented:
                raise _error(index)
            expect = False
            obj.append(result)
        elif c == term:
            return obj, index + 1
        elif not obj:
            expect = True
        elif c == ',':
            expect = True
            index += 1
        else:
            raise _error(index)
    raise _error(index, 'Unfinished sequence, started at index {}')


def parse_array(pinfo, string, index):
    if string[index] == '[':
        return _parse_list(pinfo, string, index + 1, term=']')
    return NotImplemented, index


def _pair(pinfo, string, index):
    key, index = pinfo['parsers']['string'](pinfo, string, index)
    if key is NotImplemented:
        return NotImplemented, index
    length = len(string)
    while index < length and string[index].isspace():
        index += 1
    if string[index] != ':':
        return NotImplemented, index
    index += 1
    while index < length and string[index].isspace():
        index += 1
    val, index = pinfo['parse'](pinfo, string, index)
    if val is NotImplemented:
        return NotImplemented, index
    return (key, val), index


def parse_object(pinfo, string, index):
    if string[index] == '{':
        obj, index = _parse_list(pinfo, string, index + 1, _pair, term='}')
        return DeferredDict(obj), index
    return NotImplemented, index


def _parse_selector_chain(pinfo, string, index):
    chain = DeferredList()
    parse_value = pinfo['parse']
    m = _chainmatch(string, index)
    length = len(string)
    while m:
        attr, div = m.groups()
        try:
            attr = int(attr)
        except ValueError:
            pass
        index = m.end()
        if div:
            val, index = parse_value(pinfo, string, index)
            if val is NotImplemented:
                raise _error(index)
            elif isinstance(val, DeferredValue):
                chain.append(DeferredList((attr, val)))
            else:
                chain.append((attr, val))
        else:
            chain.append(attr)
        if index < length and string[index] == ';':
            index += 1
        m = _chainmatch(string, index)
    return chain, index
_ident = r'[^\d\W]\w*'
_chainmatch = re.compile('\.(-?[0-9]+|' + _ident + ')(:)?', re.U).match


@with_parsers(_chain=_parse_selector_chain)
def parse_selector(pinfo, string, index):
    m = _smatch(string, index)
    if m:
        stype = m.group()
        index += len(stype)
        if stype[0] == '\\':
            try:
                stype = pinfo['deferred'][int(stype[1:])]
            except IndexError:
                msg = '"{}" is a deferred value that has not yet been defined.'
                raise ValueError(msg.format(stype))
        elif stype == 'model:':
            try:
                model = _modelmatch(string, index).group()
            except AttributeError:
                msg = '"model" selector type must be followed by a model name.'
                raise ValueError(msg)
            index += len(model)
            stype = ('model', model)
        elif stype == 'const:':
            value, index = pinfo['parse'](pinfo, string, index)
            if value is NotImplemented:
                raise _error(index, 'Invalid const selector at index {}')
            # const type doesn't accept a chain, so we'll just return now
            return Selector(('const', value), None), index
        elif stype != 'extra':
            stype = int(stype[7:])

        chain, index = pinfo['parsers']['_chain'](pinfo, string, index)
        if isinstance(stype, DeferredValue) and not chain:
            # No point wrapping a deferred value in another deferred value.
            return stype, index
        return Selector(stype, chain), index
    return NotImplemented, index
_smatch = re.compile(r'object:\d+|extra|const:|model:|\\\d+').match
_modelmatch = re.compile(_ident + '\.' + _ident, re.U).match


def parse_function(pinfo, string, index):
    m = _funcmatch(string, index)
    if m:
        func = m.group(1)
        args, index = _parse_list(pinfo, string, m.end())
        return Function(func, args), index
    return NotImplemented, index
_funcmatch = re.compile('(' + '|'.join(Function.FUNCS) + ')\(').match

_deferred = (
    ('selector', parse_selector),
    ('function', parse_function),
)
_values = _deferred + (
    ('object', parse_object),
    ('array', parse_array),
    ('string', parse_string),
    ('datetime', parse_datetime),
    ('date', parse_date),
    ('time', parse_time),
    ('number', parse_number),
    ('const', parse_const),
)

parse_value = subparser(parseloop, parse=parseloop, parsers=_values)
parse_deferred = subparser(parseloop, parse=parse_value, parsers=_deferred)


@subparser(parse=parse_deferred)
def parse_deferred_list(pinfo, string, index):
    pinfo['deferred'] = deferred = []
    if string[index:index + 5] == 'with(':
        return _parse_list(pinfo, string, index + 5, obj=deferred, expect=True)
    return deferred, index


def parse_operator(pinfo, string, index):
    m = _opmatch(string, index)
    if m:
        return m.group(1), m.end()
    return NotImplemented, index
# NOTE <= appears before < and >= appears before > in the list.
_ops = '==|!=|<=|<|>=|>|like|not like|re|exists|does not exist|bool|in|not in'
_opmatch = re.compile('\s+(' + _ops + ')').match


@with_parsers(value=parse_value, operator=parse_operator)
def parse_condition(pinfo, string, index):
    parse_value = pinfo['parsers']['value']
    left, index = parse_value(pinfo, string, index)
    if left is NotImplemented:
        return NotImplemented, index
    elif not isinstance(left, DeferredValue):
        left = Selector(('const', left), ())
    op, index = pinfo['parsers']['operator'](pinfo, string, index)
    if op is NotImplemented:
        raise _error(index, 'Expected operator at index {}')
    elif Condition.is_unary(op):
        return Condition(left=left, operator=op), index

    ws = False
    length = len(string)
    while index < length and string[index].isspace():
        ws = True
        index += 1
    if not ws:
        raise _error(index, 'Binary operator must have whitespace at index {}')
    right, index = parse_value(pinfo, string, index)
    if right is NotImplemented:
        raise _error(index, 'Expected deferred value at index {}')
    elif not isinstance(right, DeferredValue):
        right = Selector(('const', right), ())
    return Condition(left=left, operator=op, right=right), index


def parse_tree(pinfo, string, index):
    node = ConditionNode()
    conn = node.default
    negate_next = False
    expect = -1
    length = len(string)
    parse = pinfo['parse']
    parse_condition = pinfo['parsers']['condition']
    while index < length:
        if expect:
            m = _expectmatch(string, index)
            index = m.end()
            sym = m.group(1)
            if sym and sym[0] == 'N':
                negate_next = not negate_next
                continue
            elif sym and sym[0] == '(':
                result, index = parse(pinfo, string, index)
                while index < length and string[index].isspace():
                    index += 1
                if index >= length or string[index] != ')':
                    raise _error(index, 'Expected ")" at index {}')
                index += 1
            else:
                result, index = parse_condition(pinfo, string, index)
            if result is NotImplemented:
                if expect < 0:
                    break
                raise _error(index, 'Expected condition or subtree at {}')
            if negate_next:
                result.negate()
                negate_next = False
            expect = 0
            node.add(result, conn)
        else:
            m = _connmatch(string, index)
            if m:
                index = m.end()
                conn = m.group(1)
                expect = 1
            else:
                break
    if expect > 0:
        raise _error(index, 'Expected condition at index {}')
    return node, index
_expectmatch = re.compile(r'\s*(NOT\s+|\(\s*)?').match
_connmatch = re.compile(r'\s+(AND|OR)\s+').match

parse_tree = subparser(parse_tree, parse=parse_tree,
                       parsers=[('condition', parse_condition)])


class RuleParser(Parser):
    PARSERS = (
        ('_deferred_list', parse_deferred_list),
        ('tree', parse_tree),
    )

    @staticmethod
    def _parse(pinfo, string, index):
        length = len(string)
        while index < length and string[index].isspace():
            index += 1
        index = pinfo['parsers']['_deferred_list'](pinfo, string, index)[1]
        tree, index = pinfo['parse'](pinfo, string, index)
        tree.collapse()
        # Eat any extra whitespace at the end
        while index < length and string[index].isspace():
            index += 1
        return tree, index
parse_rule = RuleParser().parse
