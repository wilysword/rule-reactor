import datetime
from collections import OrderedDict
from django.test import TestCase
from django.contrib.contenttypes.models import ContentType as CT

from madlibs.parser import parseloop
from rules.parser import (
    parse_number, parse_const, parse_string, parse_array, parse_object,
    parse_function, parse_selector, _parse_selector_chain, parse_value,
    parse_deferred, parse_deferred_list, parse_operator, parse_condition,
    parse_tree, parse_rule
)
from rules.deferred import *
from rules.core import *

NORES = (NotImplemented, 0)
dlist = lambda *a: DeferredTuple(a)


class TestSimpleParsers(TestCase):
    def test_parse_const(self):
        self.assertEqual(parse_const(None, 'null', 0), (None, 4))
        self.assertEqual(parse_const(None, 'true', 0), (True, 4))
        self.assertEqual(parse_const(None, 'false', 0), (False, 5))
        self.assertEqual(parse_const(None, 'afgkjsdghnullsdfsdf', 9), (None, 13))
        self.assertEqual(parse_const(None, 'sdfnull', 0), NORES)
        self.assertEqual(parse_const(None, 'null', 1), (NotImplemented, 1))
        self.assertEqual(parse_const(None, 'nul', 0), NORES)
        self.assertEqual(parse_const(None, 'Null', 0), NORES)

    def test_parse_number_int(self):
        self.assertEqual(parse_number(None, '234', 0), (234, 3))
        self.assertEqual(parse_number(None, '234234234', 6), (234, 9))
        self.assertEqual(parse_number(None, '-234', 0), (-234, 4))
        self.assertEqual(parse_number(None, '-234', 1), (234, 4))
        self.assertEqual(parse_number(None, '345-234', 3), (-234, 7))
        self.assertEqual(parse_number(None, '234abc', 0), (234, 3))
        self.assertEqual(parse_number(None, '0', 0), (0, 1))
        self.assertEqual(parse_number(None, '0234', 0), (0, 1))
        self.assertEqual(parse_number(None, '-0234', 0), NORES)
        self.assertEqual(parse_number(None, 'abc', 0), NORES)
        self.assertEqual(parse_number(None, '-abc', 0), NORES)

    def test_parse_number_float(self):
        self.assertEqual(parse_number(None, '234.', 0), (234, 4))
        self.assertEqual(parse_number(None, '2343780.4', 6), (.4, 9))
        self.assertEqual(parse_number(None, '-234.', 0), (-234, 5))
        self.assertEqual(parse_number(None, '0.100', 3), (0, 4))
        self.assertEqual(parse_number(None, '0.100', 0), (.1, 5))
        self.assertEqual(parse_number(None, '0.1234.45', 0), (.1234, 6))
        self.assertEqual(parse_number(None, '02.34', 0), (0, 1))
        self.assertEqual(parse_number(None, '-02.4', 0), NORES)
        self.assertEqual(parse_number(None, 'a.234', 0), NORES)
        self.assertEqual(parse_number(None, '-a.bc', 0), NORES)
        self.assertEqual(parse_number(None, '-.234', 0), NORES)
        self.assertEqual(parse_number(None, '.234', 0), NORES)

    def test_parse_number_float_const(self):
        x, i = parse_number(None, 'nan', 0)
        self.assertEqual((str(x), i), ('nan', 3))
        x, i = parse_number(None, 'Nan', 0)
        self.assertEqual((str(x), i), ('nan', 3))
        x, i = parse_number(None, 'nAN', 0)
        self.assertEqual((str(x), i), ('nan', 3))
        x, i = parse_number(None, 'abcnandef', 3)
        self.assertEqual((str(x), i), ('nan', 6))
        self.assertEqual(parse_number(None, '-nan', 0), NORES)
        inf = float('inf')
        self.assertEqual(parse_number(None, 'inf', 0), (inf, 3))
        self.assertEqual(parse_number(None, '-inf', 0), (-inf, 4))
        self.assertEqual(parse_number(None, 'INf', 0), (inf, 3))
        self.assertEqual(parse_number(None, 'inFIniTY', 0), (inf, 8))
        self.assertEqual(parse_number(None, '-infINIty', 0), (-inf, 9))
        self.assertEqual(parse_number(None, 'qxzinfygh', 3), (inf, 6))
        self.assertEqual(parse_number(None, '-infini', 0), (-inf, 4))

    def test_parse_number_exp(self):
        self.assertEqual(parse_number(None, '1e2', 0), (100., 3))
        self.assertEqual(parse_number(None, '1e-2', 0), (.01, 4))
        self.assertEqual(parse_number(None, '1E2', 0), (100., 3))
        self.assertEqual(parse_number(None, '1e', 0), (1, 1))
        self.assertEqual(parse_number(None, '1e+2', 0), (100, 4))
        self.assertEqual(parse_number(None, '1.23e2', 0), (123, 6))
        self.assertEqual(parse_number(None, '2341.23e2', 3), (123, 9))

    def test_parse_string(self):
        self.assertEqual(parse_string(None, '"hello"', 0), ('hello', 7))
        self.assertEqual(parse_string(None, 'sdf"hello"gef', 3), ('hello', 10))
        self.assertEqual(parse_string(None, 'sdf"hello"', 0), NORES)
        self.assertEqual(parse_string(None, '', 0), NORES)
        self.assertRaises(ValueError, parse_string, None, '"hello', 0)
        # Uses standard library's json.decoder.scanstring, so we'll assume it works.


class TestParseArray(TestCase):
    pinfo = {'parse': parseloop,
             'parsers': OrderedDict([
                 ('string', parse_string),
                 ('number', parse_number),
                 ('const', parse_const),
                 ('array', parse_array),
             ])}

    def p(self, string, index=0):
        return parse_array(self.pinfo, string, index)

    def test_parse(self):
        a = ('[1]', 0)
        self.assertRaises(TypeError, parse_array, None, *a)
        pi = {}
        self.assertRaises(KeyError, parse_array, pi, *a)
        pi['parse'] = NotImplemented
        self.assertRaises(TypeError, parse_array, pi, *a)
        pi['parse'] = parseloop
        pi['parsers'] = {'array': parse_array}
        self.assertEqual(parse_array(pi, '[]', 0), (dlist(), 2))

    def test_parse_empty(self):
        empty = dlist()
        self.assertEqual(self.p('[]'), (empty, 2))
        self.assertEqual(self.p('[ \r\t\n]'), (empty, 6))
        self.assertEqual(self.p('sdf sg[  ]hello', 6), (empty, 10))
        self.assertEqual(self.p(' []'), NORES)
        self.assertRaises(ValueError, self.p, '[')
        self.assertRaises(ValueError, self.p, '[}')

    def test_parse_nonempty(self):
        l = dlist(3, 'hello', True)
        self.assertEqual(self.p('[3,"hello",true]'), (l, 16))
        self.assertEqual(self.p('[  3,\t\n"hello"\r, true ]  '), (l, 23))
        self.assertEqual(self.p('sdhf[3, "hello", true]sdf', 4), (l, 22))
        self.assertRaises(ValueError, self.p, '[ 3 4]')
        self.assertRaises(ValueError, self.p, '[ 3, ]')
        self.assertRaises(ValueError, self.p, '[ abc ]')
        self.assertRaises(ValueError, self.p, '[ 3, 4')
        self.assertRaises(ValueError, self.p, '[ ,3, 4]')
        self.assertRaises(ValueError, self.p, '[00.3]')

    def test_parse_recursive(self):
        li = dlist(3, 4)
        lo = dlist(4, li, 'hi')
        self.assertEqual(self.p('[4,[3,4],"hi"]'), (lo, 14))
        self.assertEqual(self.p('[4, [ 3, 4 ] , "hi" ]'), (lo, 21))
        self.assertEqual(self.p('234bds [4,[3,4],"hi"]', 7), (lo, 21))
        self.assertRaises(ValueError, self.p, '[4,[3,4,"hi"]')
        self.assertRaises(ValueError, self.p, '[4,[3,4],"hi"')
        self.assertRaises(ValueError, self.p, '[4,[3,4],"hi]"')


class TestParseObject(TestCase):
    pinfo = {'parse': parseloop,
             'parsers': OrderedDict([
                 ('string', parse_string),
                 ('number', parse_number),
                 ('const', parse_const),
                 ('object', parse_object),
             ])}

    def p(self, string, index=0):
        return parse_object(self.pinfo, string, index)

    def test_parse(self):
        a = ('{"":""}', 0)
        self.assertRaises(TypeError, parse_object, None, *a)
        pi = {}
        self.assertRaises(KeyError, parse_object, pi, *a)
        pi['parse'] = parseloop
        pi['parsers'] = {}
        self.assertRaises(KeyError, parse_object, pi, *a)
        pi['parsers']['string'] = parse_string
        self.assertEqual(parse_object(pi, *a), (DeferredDict([('', '')]), 7))

    def test_parse_empty(self):
        empty = DeferredDict()
        self.assertEqual(self.p('{}'), (empty, 2))
        self.assertEqual(self.p('{ \r\t\n}'), (empty, 6))
        self.assertEqual(self.p('sdf sg{  }hello', 6), (empty, 10))
        self.assertEqual(self.p(' {}'), NORES)
        self.assertRaises(ValueError, self.p, '{')
        self.assertRaises(ValueError, self.p, '{"",')
        self.assertRaises(ValueError, self.p, '{]')

    def test_parse_nonempty(self):
        d = {'hey': 5, 'you': True, 'good': 'bye'}
        d = DeferredDict(d)
        self.assertEqual(self.p('{"hey":5,"you":true,"good":"bye"}'), (d, 33))
        self.assertEqual(self.p('{ "hey" :\t5\n,\r"you" : true, '
                                ' "good" : "bye"           }'), (d, 55))
        self.assertEqual(self.p('doifhg{"hey":5,"you":true,"good":"bye"}si', 6), (d, 39))
        self.assertRaises(ValueError, self.p, '{5:5}')
        self.assertRaises(ValueError, self.p, '{"5:5}')
        self.assertRaises(ValueError, self.p, '{,"5":5}')
        self.assertRaises(ValueError, self.p, '{"5":5,}')
        self.assertRaises(ValueError, self.p, '{"5":5,5}')
        self.assertRaises(ValueError, self.p, '{"5":}')
        self.assertRaises(ValueError, self.p, '{"5" 5}')
        self.assertRaises(ValueError, self.p, '{"5", 5}')
        self.assertRaises(ValueError, self.p, '{"5": abc}')
        self.assertRaises(ValueError, self.p, '{"5": 05}')
        self.assertRaises(ValueError, self.p, '{"5":5')

    def test_parse_recursive(self):
        di = DeferredDict({'hey': None})
        d = DeferredDict({'you': di, '4': 5})
        self.assertEqual(self.p('{"you":{"hey":null},"4":5}'), (d, 26))
        self.assertEqual(self.p('{ "you" : {  "hey" : null  } , "4" : 5 }'), (d, 40))
        self.assertEqual(self.p('sdhf{"you":{"hey":null},"4":5}sdf', 4), (d, 30))
        self.assertRaises(ValueError, self.p, '{"you":{"hey":null,"4":5}')
        self.assertRaises(ValueError, self.p, '{"you":{"hey":null},"4":5')
        self.assertRaises(ValueError, self.p, '{"you":{"hey"null},"4":5}')
        self.assertRaises(ValueError, self.p, '{"you":{"hey",null},"4":5}')
        self.assertRaises(ValueError, self.p, '{"you":"hey":null},"4":5}')


class TestParseFunction(TestCase):
    pinfo = {'parse': parseloop,
             'parsers': {
                 'string': parse_string,
                 'number': parse_number,
                 'function': parse_function,
                 'object': parse_object,
            }}

    def p(self, string, index=0):
        return parse_function(self.pinfo, string, index)

    def test_parse(self):
        a = ('min()', 0)
        self.assertRaises(TypeError, parse_function, None, *a)
        pi = {}
        self.assertRaises(KeyError, parse_function, pi, *a)
        pi['parse'] = parseloop
        pi['parsers'] = {}
        self.assertEqual(parse_function(pi, *a), (Function('min', ()), 5))

    def test_parse_noargs(self):
        f = Function('min', ())
        self.assertEqual(self.p('min()'), (f, 5))
        self.assertEqual(self.p('min(  \t )'), (f, 9))
        self.assertEqual(self.p('sdfmin( )sdfs', 3), (f, 9))
        self.assertEqual(self.p(' min()'), NORES)
        self.assertEqual(self.p('min ()'), NORES)
        self.assertEqual(self.p('abc()'), NORES)
        self.assertRaises(ValueError, self.p, 'min(')
        for func in Function.FUNCS:
            self.assertEqual(self.p(func + '()'), (Function(func, ()), len(func) + 2))

    def test_parse_constargs(self):
        f = Function('min', (5, {'hi': 4}))
        self.assertEqual(self.p('min(5,{"hi":4})'), (f, 15))
        self.assertEqual(self.p('min(  5\r ,\n {"hi":4}\t  )'), (f, 24))
        self.assertEqual(self.p('xsfmin(5,{"hi":4})sdf', 3), (f, 18))
        self.assertRaises(ValueError, self.p, 'min(5')
        self.assertRaises(ValueError, self.p, 'min(5 6)')
        self.assertRaises(ValueError, self.p, 'min(,)')
        self.assertRaises(ValueError, self.p, 'min(5,)')
        self.assertRaises(ValueError, self.p, 'min(,5)')
        self.assertRaises(ValueError, self.p, 'min("5)')
        self.assertRaises(ValueError, self.p, 'min(min)')

    def test_recursive(self):
        f = Function('min', (Function('max', (2, 4)), 5))
        self.assertEqual(self.p('min(max(2,4),5)'), (f, 15))
        self.assertEqual(self.p('min(\nmax(\r2 , 4 ),5 )'), (f, 21))
        self.assertEqual(self.p('bgsjdbmin(max(2,4),5)', 6), (f, 21))
        self.assertRaises(ValueError, self.p, 'min(max (2,4),5)')
        self.assertRaises(ValueError, self.p, 'min(max2,4),5)')
        self.assertRaises(ValueError, self.p, 'min(max(2,4,5)')
        self.assertRaises(ValueError, self.p, 'min(max(2,4),5')


class TestParseSelector(TestCase):
    pinfo = {'parse': parseloop,
             'parsers': {
                 'string': parse_string,
                 'number': parse_number,
                 'function': parse_function,
                 'selector': parse_selector,
            }}

    def p(self, string, index=0):
        return parse_selector(self.pinfo, string, index)

    def c(self, string, index=0):
        return _parse_selector_chain(self.pinfo, string, index)

    def test_parse(self):
        a = ('extra', 0)
        self.assertRaises(TypeError, parse_selector, None, *a)
        pi = {}
        self.assertRaises(KeyError, parse_selector, pi, *a)
        pi['deferred'] = []
        self.assertRaises(KeyError, parse_selector, pi, *a)
        pi['parsers'] = {}
        self.assertRaises(KeyError, parse_selector, pi, *a)
        pi['parsers']['_chain'] = _parse_selector_chain
        self.assertRaises(KeyError, parse_selector, pi, *a)
        pi['parse'] = parseloop
        self.assertEqual(parse_selector(pi, *a), (Selector('extra', ()), 5))

    def test_chain_single(self):
        NORES = ([], 0)
        self.assertEqual(self.c('hello'), NORES)
        self.assertEqual(self.c('3'), NORES)
        self.assertEqual(self.c('hello.'), NORES)
        self.assertEqual(self.c('.'), NORES)
        self.assertEqual(self.c('.hello'), (['hello'], 6))
        self.assertEqual(self.c('.hello;'), (['hello'], 7))
        self.assertEqual(self.c('.234hello'), ([234], 4))
        self.assertEqual(self.c('.-234hello'), ([-234], 5))
        self.assertEqual(self.c('.hel-2lo'), (['hel'], 4))
        self.assertEqual(self.c('hey.hello', 3), (['hello'], 9))
        self.assertEqual(self.c('.heL_lo'), (['heL_lo'], 7))

    def test_chain_arg(self):
        self.assertEqual(self.c('.hey:1'), ([dlist('hey', 1)], 6))
        self.assertEqual(self.c('.hey:1,2'), ([dlist('hey', 1)], 6))
        f = Function('min', (1, 2))
        self.assertEqual(self.c('.hey:min(1,2)'), ([dlist('hey', f)], 13))
        self.assertEqual(self.c('.hey:min( 1 , 2 )'), ([dlist('hey', f)], 17))
        self.assertRaises(ValueError, self.c, '.hey: min(1,2)')
        self.assertRaises(ValueError, self.c, '.hey:min (1,2)')

    def test_chain_multiple(self):
        self.assertEqual(self.c('.hey.hi'), (['hey', 'hi'], 7))
        self.assertEqual(self.c('.2.hi'), ([2, 'hi'], 5))
        self.assertEqual(self.c('.hey:3.hi'), ([dlist('hey', 3.)], 7))
        self.assertEqual(self.c('.hey:3..hi'), ([dlist('hey', 3.), 'hi'], 10))
        self.assertEqual(self.c('.hey:3.3.hi'), ([dlist('hey', 3.3), 'hi'], 11))
        self.assertEqual(self.c('.hey:3;.3.hi'), ([dlist('hey', 3), 3, 'hi'], 12))
        f = Function('min', ())
        self.assertEqual(self.c('.hey.hi:min()'), (['hey', dlist('hi', f)], 13))
        self.assertEqual(self.c('.hey.hi:min();'), (['hey', dlist('hi', f)], 14))
        self.assertEqual(self.c('hello.hey.hi', 5), (['hey', 'hi'], 12))
        self.assertRaises(ValueError, self.c, '.hey.hi:yo')

    def test_selector_deferred(self):
        f = Function('min', (1, 2))
        self.pinfo['deferred'] = [f]
        self.assertRaises(ValueError, self.p, r'\1')
        self.assertEqual(self.p(r'\0'), (f, 2))
        self.assertEqual(len(self.pinfo['deferred']), 1)
        s = Selector(f, [1, 'hi'])
        self.assertEqual(self.p(r'\0.1.hi'), (s, 7))
        self.assertEqual(self.p(r'\1\0.1.hi;hello', 2), (s, 10))
        self.assertEqual(self.p(r'\0 .1.hi'), (f, 2))
        self.assertEqual(self.p(r'\0i.1.hi'), (f, 2))
        self.assertRaises(ValueError, self.p, r'\0.hi:yo')
        self.assertEqual(self.p('0'), NORES)

    def test_selector_model(self):
        s = Selector(('model', 'contenttypes.contenttype'), ('hey',))
        self.assertEqual(self.p('model'), NORES)
        self.assertEqual(self.p('model :'), NORES)
        self.assertRaises(ValueError, self.p, 'model:')
        self.assertRaises(ValueError, self.p, 'model:hello')
        self.assertRaises(CT.DoesNotExist, self.p, 'model:hello.model')
        self.assertRaises(ValueError, self.p, 'model: contenttypes.contenttype')
        self.assertRaises(ValueError, self.p, 'model:contenttypes. contenttype')
        self.assertRaises(ValueError, self.p, 'model:contenttypes .contenttype')
        self.assertEqual(self.p('model:contenttypes.contenttype.hey'), (s, 34))
        self.assertEqual(self.p('bsdfgmodel:contenttypes.contenttype.hey-3', 5), (s, 39))

    def test_selector_const(self):
        s = Selector(('const', 'hey'), ())
        self.assertEqual(self.p('const'), NORES)
        self.assertEqual(self.p('const :'), NORES)
        self.assertRaises(ValueError, self.p, 'const:')
        self.assertRaises(ValueError, self.p, 'const:hello')
        self.assertRaises(ValueError, self.p, 'const: "hey"')
        self.assertEqual(self.p('const:"hey"'), (s, 11))
        self.assertEqual(self.p('sdfconst:"hey"sdfs', 3), (s, 14))
        self.assertEqual(self.p('const:"hey".hello.0'), (s, 11))
        self.assertRaises(ValueError, self.p, 'const:min()')
        self.assertRaises(ValueError, self.p, 'const:[min()]')

    def test_selector_objects(self):
        s = Selector(0, ())
        self.assertEqual(self.p('object'), NORES)
        self.assertEqual(self.p('object :'), NORES)
        self.assertEqual(self.p('object:'), NORES)
        self.assertEqual(self.p('object:one'), NORES)
        self.assertEqual(self.p('object:-1'), NORES)
        self.assertEqual(self.p('object: 1'), NORES)
        self.assertEqual(self.p('object:0'), (s, 8))
        self.assertEqual(self.p('sjkgdobject:0.-sdg', 5), (s, 13))
        self.assertEqual(self.p('object:1.1'), (Selector(1, (1,)), 10))
        self.assertRaises(ValueError, self.p, 'object:1.hey:you')


SAMPLES = {
    'selector': 'object:0.split:"."',
    'function': 'max(1, 2)',
    'object': '{"one": 1, "two": "dos"}',
    'array': '[1.1, "you", 2014-02-28]',
    'string': r'"\"Hello,\" he said."',
    'datetime': '1984-10-28 01:01:12.34',
    'date': '2014-09-18',
    'time': '16:13:35',
    'number': '-54.2e-1',
    'const': 'null'
}


class TestParseDeferred(TestCase):
    def setUp(self):
        self.pinfo = {'parse': None, 'parsers': None, 'deferred': []}

    def p(self, string, index=0):
        return parse_deferred(self.pinfo, string, index)

    def test_bad(self):
        samples = (SAMPLES[k] for k in SAMPLES if k not in ('selector', 'function'))
        for v in samples:
            self.assertEqual(self.p(v), NORES)

    def test_parse_selector(self):
        self.assertEqual(self.p('object:0'), (Selector(0, ()), 8))
        self.assertEqual(self.p('helloobject:0goodbye', 5), (Selector(0, ()), 13))
        self.assertEqual(self.p('object :0'), NORES)
        self.assertEqual(self.p(SAMPLES['selector']), (Selector(0, [dlist('split', '.')]), 18))
        self.assertEqual(self.p('.hello'), NORES)

    def test_parse_function(self):
        self.assertEqual(self.p('min()'), (Function('min', ()), 5))
        self.assertEqual(self.p('hellomin()goodbye', 5), (Function('min', ()), 10))
        self.assertEqual(self.p('min ()'), NORES)
        self.assertEqual(self.p(SAMPLES['function']), (Function('max', (1, 2)), 9))


class TestParseValue(TestParseDeferred):
    test_bad = None

    def p(self, string, index=0):
        return parse_value(self.pinfo, string, index)

    def test_parse_number(self):
        self.assertEqual(self.p('12:12'), (12, 2))
        self.assertEqual(self.p('2394712:12', 5), (12, 7))
        self.assertEqual(self.p(SAMPLES['number']), (-5.42, 8))

    def test_parse_const(self):
        self.assertEqual(self.p('true'), (True, 4))
        self.assertEqual(self.p('shdgtruesdf', 4), (True, 8))

    def test_parse_datetime(self):
        d = datetime.datetime(1984, 10, 28, 1, 1, 12, 340000)
        self.assertEqual(self.p(SAMPLES['datetime']), (d, 22))
        self.assertEqual(self.p('xyz' + SAMPLES['datetime'] + '+10', 3), (d, 25))

    def test_parse_date(self):
        d = datetime.date(2014, 9, 18)
        self.assertEqual(self.p(SAMPLES['date']), (d, 10))
        self.assertEqual(self.p('xyz' + SAMPLES['date'] + '+10', 3), (d, 13))

    def test_parse_time(self):
        d = datetime.time(16, 13, 35)
        self.assertEqual(self.p(SAMPLES['time']), (d, 8))
        self.assertEqual(self.p('xyzwv' + SAMPLES['time'] + '+10', 5), (d, 13))

    def test_parse_string(self):
        self.assertEqual(self.p('""'), ('', 2))
        self.assertEqual(self.p('shdgl"  "sdf', 5), ('  ', 9))
        self.assertEqual(self.p(' ""'), NORES)
        self.assertEqual(self.p(SAMPLES['string']), ('"Hello," he said.', 21))

    def test_parse_object(self):
        self.assertEqual(self.p('{}'), (DeferredDict(), 2))
        self.assertEqual(self.p('shdgl{    }sdf', 5), (DeferredDict(), 11))
        self.assertEqual(self.p(' {}'), NORES)
        d = DeferredDict({'one': 1, 'two': 'dos'})
        self.assertEqual(self.p(SAMPLES['object']), (d, 24))

    def test_parse_array(self):
        self.assertEqual(self.p('[]'), (dlist(), 2))
        self.assertEqual(self.p('shdgl[    ]sdf', 5), (dlist(), 11))
        self.assertEqual(self.p(' []'), NORES)
        d = datetime.date(2014, 2, 28)
        self.assertEqual(self.p(SAMPLES['array']), (dlist(1.1, 'you', d), 24))


class TestParseDeferredTuple(TestCase):
    def setUp(self):
        self.pinfo = {'parse': 0, 'parsers': {'deferred': parse_deferred}}

    def p(self, string, index=0):
        return parse_deferred_list(self.pinfo, string, index)

    def test_parse_list(self):
        self.assertRaises(ValueError, self.p, 'with(')
        self.assertRaises(ValueError, self.p, 'with()')
        self.assertEqual(self.p(' with(object:0)'), ([], 0))
        d, i = self.p('asdwith(  object:0  ,  min(2 )  ) howdy', 3)
        self.assertEqual(d, [Selector(0, None), Function('min', [2])])
        self.assertEqual(i, 33)


class TestParseCondition(TestCase):
    def setUp(self):
        self.pinfo = {'parse': 0, 'parsers': {}}

    def p(self, string, index=0):
        return parse_condition(self.pinfo, string, index)

    def test_operator(self):
        ops = set(Condition.OPERATOR_MAP) | set(Condition.NEGATED_OPERATORS)
        for op in ops:
            self.assertEqual(parse_operator({}, op, 0), NORES)
            self.assertEqual(parse_operator({}, op + ' ', 0), NORES)
            x = ' ' + op
            self.assertEqual(parse_operator({}, x, 0), (op, len(op) + 1))
            x = ' sdf ' + op + ' sdf'
            self.assertEqual(parse_operator({}, x, 4), (op, len(op) + 5))
        for op in '/*-+':
            self.assertEqual(parse_operator({}, ' ' + op, 0), NORES)

    def test_left(self):
        for key, val in SAMPLES.items():
            value = val + ' bool ' + val
            if key == 'selector':
                d, i = self.p(value)
                self.assertEqual(d.left, Selector(0, [dlist('split', '.')]))
                self.assertEqual(i, 23)
                self.assertIs(d.right, None)
            elif key == 'function':
                d, i = self.p(value)
                self.assertEqual(d.left, Function('max', (1, 2)))
                self.assertEqual(i, 14)
                self.assertIs(d.right, None)
            else:
                d = self.p(value)[0].left
                v = parse_value(self.pinfo, val, 0)[0]
                self.assertEqual(d.stype, 'const')
                self.assertEqual(d.arg, v)
        self.assertEqual(self.p('hello bool'), NORES)
        self.assertRaises(ValueError, self.p, '[min()] bool')

    def test_right(self):
        for key, val in SAMPLES.items():
            value = 'object:0 == ' + val
            if key == 'selector':
                d, i = self.p(value)
                self.assertEqual(d.right, Selector(0, [dlist('split', '.')]))
                self.assertEqual(i, 30)
            elif key == 'function':
                d, i = self.p(value)
                self.assertEqual(d.right, Function('max', (1, 2)))
                self.assertEqual(i, 21)
            else:
                d = self.p(value)[0].right
                v = parse_value(self.pinfo, val, 0)[0]
                self.assertEqual(d.stype, 'const')
                self.assertEqual(d.arg, v)
        self.assertRaises(ValueError, self.p, '"hello" == hello')
        self.assertRaises(ValueError, self.p, '"hello" == [min()]')

    def test_bad_operator(self):
        # no space before operator
        self.assertRaises(ValueError, self.p, SAMPLES['function'] + 'bool')
        # non-operator
        self.assertRaises(ValueError, self.p, SAMPLES['function'] + ' *')

    def test_unary_vs_binary(self):
        ops = set(Condition.OPERATOR_MAP) | set(Condition.NEGATED_OPERATORS)
        left = 'object:0 '
        sl = Selector(0, ())
        for op in ops:
            if Condition.is_unary(op):
                d, i = self.p(left + op)
                self.assertIs(d.right, None)
                self.assertEqual(d.left, sl)
                self.assertTrue(d.is_unary)
            else:
                self.assertRaises(ValueError, self.p, left + op)
                self.assertRaises(ValueError, self.p, left + op + ' ')


class TestParseConditionTree(TestCase):
    def setUp(self):
        self.pinfo = {'parse': 0, 'parsers': 0}

    def p(self, string, index=0):
        return parse_tree(self.pinfo, string, index)

    def test_empty(self):
        d, i = self.p('')
        self.assertTrue(d.evaluate())
        self.assertEqual(len(d.children), 0)
        self.assertEqual(i, 0)
        d, i = self.p('object:0 bool AND ()')
        self.assertEqual(len(d), 1)
        self.assertEqual(d.children[0].left, Selector(0, ()))

    def test_negation(self):
        d, i = self.p('object:0 bool')
        self.assertEqual(i, 13)
        self.assertEqual(len(d), 1)
        self.assertEqual(d.connector, 'AND')
        self.assertEqual(d.children[0].left, Selector(0, ()))
        self.assertFalse(d.negated)
        self.assertFalse(d.children[0].negated)
        d, i = self.p('NOT object:0 bool')
        self.assertEqual(i, 17)
        self.assertEqual(len(d), 1)
        self.assertEqual(d.connector, 'AND')
        self.assertEqual(d.children[0].left, Selector(0, ()))
        self.assertFalse(d.negated)
        self.assertTrue(d.children[0].negated)
        d, i = self.p('NOT NOT object:0 bool')
        self.assertEqual(i, 21)
        self.assertFalse(d.negated)
        self.assertFalse(d.children[0].negated)

    def test_parens(self):
        d, i = self.p('object:0 bool')
        self.assertEqual(i, 13)
        self.assertEqual(len(d), 1)
        self.assertEqual(d.connector, 'AND')
        self.assertEqual(d.children[0].left, Selector(0, ()))
        d, i = self.p('( object:0 bool )')
        self.assertEqual(i, 17)
        self.assertEqual(len(d), 1)
        self.assertEqual(d.connector, 'AND')
        self.assertEqual(d.children[0].left, Selector(0, ()))
        d, i = self.p('( (object:0 bool ) )')
        self.assertEqual(i, 20)
        self.assertEqual(d.children[0].left, Selector(0, ()))

    def test_multiple(self):
        d, i = self.p('object:0 bool AND min() bool')
        self.assertEqual(i, 28)
        self.assertEqual(len(d), 2)
        self.assertEqual(d.connector, 'AND')
        self.assertEqual(d.children[0].left, Selector(0, ()))
        self.assertEqual(d.children[1].left, Function('min', ()))
        d, i = self.p('(object:0 bool) OR min() bool')
        self.assertEqual(len(d), 2)
        self.assertEqual(d.connector, 'OR')
        self.assertEqual(d.children[0].left, Selector(0, ()))
        self.assertEqual(d.children[1].left, Function('min', ()))
        d, i = self.p('object:0 bool AND (min() bool)')
        self.assertEqual(len(d), 2)
        self.assertEqual(d.connector, 'AND')
        self.assertEqual(d.children[0].left, Selector(0, ()))
        self.assertEqual(d.children[1].left, Function('min', ()))
        d, i = self.p('(object:0 bool OR min() bool)')
        self.assertEqual(len(d), 1)
        self.assertEqual(d.connector, 'AND')
        self.assertEqual(d.children[0].connector, 'OR')
        self.assertEqual(d.children[0].children[0].left, Selector(0, ()))
        self.assertEqual(d.children[0].children[1].left, Function('min', ()))
        d, i = self.p('(object:0 bool AND min() bool)')
        self.assertEqual(len(d), 2)
        self.assertEqual(d.connector, 'AND')
        self.assertEqual(d.children[0].left, Selector(0, ()))
        self.assertEqual(d.children[1].left, Function('min', ()))

    def test_missing(self):
        self.assertRaises(ValueError, self.p, '(object:0 bool')
        self.assertRaises(ValueError, self.p, 'object:0 bool AND (')
        self.assertRaises(ValueError, self.p, 'object:0 bool AND x')
        self.assertRaises(ValueError, self.p, 'object:0 bool AND ')
        self.assertRaises(ValueError, self.p, 'object:0 == AND ()')

    def test_negate_multiple(self):
        d, i = self.p('NOT object:0 bool AND min() bool')
        self.assertEqual(len(d), 2)
        self.assertEqual(d.connector, 'AND')
        self.assertTrue(d.children[0].negated)
        self.assertFalse(d.children[1].negated)
        d, i = self.p('object:0 bool AND NOT min() bool')
        self.assertEqual(len(d), 2)
        self.assertEqual(d.connector, 'AND')
        self.assertFalse(d.children[0].negated)
        self.assertTrue(d.children[1].negated)
        d, i = self.p('NOT (object:0 bool AND min() bool)')
        self.assertEqual(len(d), 1)
        d = d.children[0]
        self.assertEqual(len(d), 2)
        self.assertFalse(d.negated)
        self.assertEqual(d.connector, 'OR')
        self.assertTrue(d.children[0].negated)
        self.assertTrue(d.children[1].negated)

    def test_order_of_operations(self):
        d, i = self.p('0 bool AND 1 bool OR 2 bool AND 3 bool')
        self.assertEqual(len(d), 2)
        self.assertEqual(d.connector, 'AND')
        self.assertEqual(d.children[1].left, Selector(('const', 3), ()))
        d = d.children[0]
        self.assertEqual(len(d), 2)
        self.assertEqual(d.connector, 'OR')
        self.assertEqual(d.children[1].left, Selector(('const', 2), ()))
        d = d.children[0]
        self.assertEqual(len(d), 2)
        self.assertEqual(d.connector, 'AND')
        self.assertEqual(d.children[0].left, Selector(('const', 0), ()))
        self.assertEqual(d.children[1].left, Selector(('const', 1), ()))
        d, i = self.p('((0 bool AND 1 bool) OR 2 bool) AND 3 bool')
        self.assertEqual(len(d), 2)
        self.assertEqual(d.connector, 'AND')
        self.assertEqual(d.children[1].left, Selector(('const', 3), ()))
        d = d.children[0]
        self.assertEqual(len(d), 2)
        self.assertEqual(d.connector, 'OR')
        self.assertEqual(d.children[1].left, Selector(('const', 2), ()))
        d = d.children[0]
        self.assertEqual(len(d), 2)
        self.assertEqual(d.connector, 'AND')
        self.assertEqual(d.children[0].left, Selector(('const', 0), ()))
        self.assertEqual(d.children[1].left, Selector(('const', 1), ()))


class TestParseRule(TestCase):
    def test_collapse(self):
        d = parse_rule('    NOT (object:0 bool AND min() bool)    ')
        self.assertEqual(len(d), 2)
        self.assertFalse(d.negated)
        self.assertEqual(d.connector, 'OR')
        self.assertTrue(d.children[0].negated)
        self.assertTrue(d.children[1].negated)

    def test_deferred_list(self):
        self.assertRaises(ValueError, parse_rule, 'with() ()')
        d = parse_rule(' with( object:0 )  ')
        self.assertEqual(len(d), 0)
        d = parse_rule(r'with(object:0) \0 bool AND \0 bool AND \0.0 bool')
        self.assertEqual(len(d), 3)
        self.assertIs(d.children[0].left, d.children[1].left)
        self.assertIs(d.children[0].left, d.children[2].left.stype)
