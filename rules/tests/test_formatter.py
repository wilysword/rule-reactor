from datetime import datetime, date, time
from decimal import Decimal
from django.test import TestCase
from django.utils import timezone

from rules.core import *
from rules.deferred import *
from rules.formatter import (
    _format, _format_tree, _format_cond, _format_term, _format_deferred,
    _format_func, _format_sel, _format_dict, _format_list, format_rule
)
from rules.parser import parse_value, parse_rule


class TestValues(TestCase):
    deferred = ()

    def p(self, string):
        return parse_value({'parse': 0, 'parsers': (),
                            'deferred': self.deferred}, string, 0)[0]

    def test_unknown(self):
        self.assertRaises(ValueError, _format, self, ())
        self.assertRaises(ValueError, _format_deferred, self, ())

    def test_format_datetime(self):
        dt = datetime.now()
        x = _format(dt, ())
        self.assertEqual(x, str(dt))
        d = self.p(x)
        self.assertIsNot(d, dt)
        self.assertEqual(d, dt)
        dt = timezone.now()
        if dt.tzinfo is None:
            return
        x = _format(dt, ())
        self.assertEqual(x, str(dt))
        d = self.p(x)
        self.assertIsNot(d, dt)
        self.assertEqual(d, dt)

    def test_format_time(self):
        dt = datetime.now().time()
        x = _format(dt, ())
        self.assertEqual(x, str(dt))
        d = self.p(x)
        self.assertIsNot(d, dt)
        self.assertEqual(d, dt)
        dt = timezone.now().time()
        if dt.tzinfo is None:
            return
        x = _format(dt, ())
        self.assertEqual(x, str(dt))
        d = self.p(x)
        self.assertIsNot(d, dt)
        self.assertEqual(d, dt)

    def test_format_date(self):
        dt = date.today()
        x = _format(dt, ())
        self.assertEqual(x, str(dt))
        d = self.p(x)
        self.assertIsNot(d, dt)
        self.assertEqual(d, dt)

    def test_format_string(self):
        x = "hello\"\\ you"
        y = _format(x, ())
        self.assertEqual(y, r'"hello\"\\ you"')
        self.assertEqual(x, self.p(y))

    def test_none(self):
        x = _format(None, ())
        self.assertEqual(x, 'null')
        self.assertIs(self.p(x), None)

    def test_true(self):
        x = _format(True, ())
        self.assertEqual(x, 'true')
        self.assertIs(self.p(x), True)

    def test_false(self):
        x = _format(False, ())
        self.assertEqual(x, 'false')
        self.assertIs(self.p(x), False)

    def test_int(self):
        x = _format(29386592, ())
        self.assertEqual(x, '29386592')
        self.assertEqual(self.p(x), 29386592)

    def test_float(self):
        x = _format(29386592.2345, ())
        self.assertEqual(x, '29386592.2345')
        self.assertEqual(self.p(x), 29386592.2345)
        y = float('infinity')
        x = _format(y, ())
        self.assertEqual(x, 'inf')
        self.assertEqual(self.p(x), y)
        y = float('-infinity')
        x = _format(y, ())
        self.assertEqual(x, '-inf')
        self.assertEqual(self.p(x), y)
        y = float('nan')
        x = _format(y, ())
        self.assertEqual(x, 'nan')
        z = self.p(x)
        self.assertNotEqual(z, z)

    def test_decimal(self):
        x = _format(Decimal('29386592.2345'), ())
        self.assertEqual(x, '29386592.2345')
        self.assertEqual(self.p(x), 29386592.2345)

    def test_list(self):
        self.assertEqual(_format([], ()), '[]')
        x = (3, 34.63, ('hello', date(2014, 10, 28)), '0')
        y = _format(x, ())
        z = '[3,34.63,["hello",2014-10-28],"0"]'
        self.assertEqual(y, z)
        self.assertEqual(self.p(y), x)
        w = list(x)
        w[2] = list(w[2])
        y = _format(w, ())
        self.assertEqual(y, z)
        self.assertEqual(self.p(y), x)

    def test_dict(self):
        from collections import OrderedDict
        self.assertEqual(_format({}, ()), '{}')
        x = OrderedDict([('hi', 3), ('yo', ('ouch',)), ('now', {'then': date(2014, 5, 24)})])
        y = _format(x, ())
        self.assertEqual(y, '{"hi":3,"yo":["ouch"],"now":{"then":2014-05-24}}')
        z = self.p(y)
        self.assertEqual(set(x.keys()), set(z.keys()))
        for k in x:
            self.assertEqual(x[k], z[k])
        self.assertRaises(TypeError, _format, {4: 13}, ())
        self.assertRaises(TypeError, _format, {(): 13}, ())

    def test_const_selector(self):
        x = Selector(('const', 42), None)
        self.assertRaises(IndexError, _format, x, ())
        self.assertRaises(AttributeError, _format, x, ((),))
        self.assertRaises(AttributeError, _format, x, ([],))
        d = [[]]
        y = _format(x, d)
        self.assertIs(d[1], x)
        self.assertEqual(y, '\\0')
        self.assertEqual(d[0][0], 'const:42')
        self.assertEqual(self.p(d[0][0]), x)
        x = Selector(('const', ('hey',)), None)
        y = _format(x, d)
        self.assertIs(d[2], x)
        self.assertEqual(y, '\\1')
        self.assertEqual(d[0][1], 'const:["hey"]')
        self.assertEqual(self.p(d[0][1]), x)

    def test_object_selector(self):
        d = [[]]
        # Incorrect tuple lengths
        self.assertRaises(ValueError, _format, Selector(0, [(1, 2, 3)]), d)
        self.assertRaises(ValueError, _format, Selector(0, [(1,)]), d)
        x = Selector(5, ['one', 'two', ('three', 'four')])
        y = _format(x, d)
        self.assertIs(d[1], x)
        self.assertEqual(y, '\\0')
        self.assertEqual(d[0][0], 'object:5.one;.two;.three:"four";')
        self.assertEqual(self.p(d[0][0]), x)

    def test_deferred_selector(self):
        d = [[]]
        s1 = Selector(0, ['hey'])
        s2 = Selector(s1, ['ho'])
        y = _format(s2, d)
        self.assertIs(d[1], s1)
        self.assertIs(d[2], s2)
        self.assertEqual(y, '\\1')
        self.assertEqual(d[0][0], 'object:0.hey;')
        self.assertEqual(d[0][1], '\\0.ho;')
        self.deferred = [s1]
        self.assertEqual(self.p(d[0][1]), s2)

    def test_extra_selector(self):
        d = [[]]
        x = Selector('extra', ['one', 'two', ('three', 'four')])
        y = _format(x, d)
        self.assertIs(d[1], x)
        self.assertEqual(y, '\\0')
        self.assertEqual(d[0][0], 'extra.one;.two;.three:"four";')
        self.assertEqual(self.p(d[0][0]), x)

    def test_model_selector(self):
        d = [[]]
        x = Selector(('model', 'contenttypes.contenttype'), ['one', 'two', ('three', 'four')])
        y = _format(x, d)
        self.assertIs(d[1], x)
        self.assertEqual(y, '\\0')
        self.assertEqual(d[0][0], 'model:contenttypes.contenttype.one;.two;.three:"four";')
        self.assertEqual(self.p(d[0][0]), x)

    def test_function(self):
        x = Function('min', [3, 'hey'])
        self.assertRaises(IndexError, _format, x, ())
        self.assertRaises(AttributeError, _format, x, ((),))
        self.assertRaises(AttributeError, _format, x, ([],))
        d = [[]]
        y = _format(x, d)
        self.assertIs(d[1], x)
        self.assertEqual(y, '\\0')
        self.assertEqual(d[0][0], 'min(3,"hey")')
        self.assertEqual(self.p(d[0][0]), x)


class TestRules(TestCase):
    def assertEq(self, node1, node2):
        self.assertEqual(len(node1), len(node2))
        self.assertEqual(node1.connector, node2.connector)
        for c1, c2 in zip(node1.children, node2.children):
            if isinstance(c1, Condition) and isinstance(c2, Condition):
                self.assertEqual(c1.negated, c2.negated)
                self.assertEqual(c1.left, c2.left)
                self.assertEqual(c1.operator, c2.operator)
                self.assertEqual(c1.right, c2.right)
            elif isinstance(c1, ConditionNode) and isinstance(c2, ConditionNode):
                self.assertEq(c1, c2)
            else:
                assert False

    def test(self):
        s = Selector(0, None)
        c1 = Condition(Selector(s, ('hey',)), 'bool')
        c2 = Condition(Function('min', ('hi', 'bye')), '==', Selector('extra', ['greeting']))
        c3 = Condition(Selector(1, ['split']), '!=', Selector(('const', ('one',)), ()))
        c4 = Condition(Selector(s, ('ho',)), '>', Selector(2, None), negated=True)
        n1 = ConditionNode([c1, c2], connector='OR')
        n2 = ConditionNode([c3], connector='OR')
        n3 = ConditionNode([c4, n1, n2])
        x = format_rule(n3)
        n3.collapse()
        y = (r'with(object:0,\0.ho;,object:2,\0.hey;,min("hi","bye"),'
             r'extra.greeting;,object:1.split;) '
             r'(NOT \1 > \2 AND (\3 bool OR \4 == \5) AND (\6 != ["one"]))')
        self.assertEqual(x, y)
        z = parse_rule(y)
        self.assertEq(z, n3)
