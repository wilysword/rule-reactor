import datetime

from django.test import TestCase
from madlibs.test_utils import CollectMixin

from rules.core import AND, OR, ConditionNode, Condition, Rule
from rules.deferred import Function, Selector, DeferredDict
from rules.continuations import store
from . import Dummy

store = store.copy()
store.clear()


class TestCondition(TestCase):
    def test_neg_ops(self):
        nops = {'not like': 'like', 'does not exist': 'exists', 'not in': 'in'}
        self.assertEqual(Condition.NEGATED_OPERATORS, nops)

    def test_op_map(self):
        om = {'!=', '==', 'like', 're', 'in', '>=', '<', '<=', '>', 'bool', 'exists'}
        self.assertEqual(set(Condition.OPERATOR_MAP), om)

    def test_is_unary(self):
        unaries = ('bool', 'exists', 'does not exist')
        self.assertEqual(set(unaries), Condition.UNARY_OPERATORS)
        ops = set(Condition.OPERATOR_MAP)
        for o in ops:
            assertion = self.assertTrue if o in unaries else self.assertFalse
            assertion(Condition.is_unary(o))

    def test_init(self):
        self.assertRaises(TypeError, Condition, random_kwarg='random value')

    def test_init_left(self):
        l = Function('percent', (30, 100))
        c = Condition(left=l, operator='bool')
        self.assertIs(c.left, l)
        self.assertIs(c.right, None)
        l = Selector(0, None)
        c = Condition(left=l, operator='bool')
        self.assertIs(c.left, l)

    def test_init_negated(self):
        kwargs = {'operator': 'bool', 'left': Function('percent', (30, 100))}
        c = Condition(**kwargs)
        self.assertIs(c.negated, False)
        c = Condition(negated=True, **kwargs)
        self.assertIs(c.negated, True)
        c = Condition(negated={}, **kwargs)
        self.assertIs(c.negated, False)
        c = Condition(negated=[1], **kwargs)
        self.assertIs(c.negated, True)

    def test_init_operator(self):
        kwargs = {'left': Function('percent', (30, 100)), 'right': Function('max', (1, 2))}
        ops = set(Condition.OPERATOR_MAP)
        for op in ops:
            c = Condition(operator=op, **kwargs)
            self.assertIs(c._eval, Condition.OPERATOR_MAP[op])
            self.assertIs(c.negated, op in Condition.NEGATED_OPERATORS)
        self.assertRaises(KeyError, Condition, operator='*', **kwargs)

    def test_init_right(self):
        l = Selector(0, None)
        r = Selector(('const', 5), None)
        c = Condition(left=l, right=r, operator='==')
        self.assertIs(c.right, r)
        r = Selector(1, None)
        c = Condition(left=l, right=r, operator='==')
        self.assertIs(c.right, r)

    def test_C_shortcut(self):
        l = r = Selector(0, None)
        kwargs = {'left': l, 'right': r, 'operator': '=='}
        cn = Condition.C(kwargs, Condition(**kwargs))
        self.assertEqual(len(cn), 2)
        self.assertEqual(cn.connector, ConditionNode.default)
        self.assertEqual(len(Condition.C()), 0)


class TestConditionMethods(CollectMixin, TestCase):
    defaults = {'left': Selector(0, None), 'right': Selector(1, None), 'operator': '=='}

    def c(self, **kwargs):
        return Condition(**self._collect('defaults', kwargs))

    def test_str(self):
        c = self.c()
        self.assertEqual(str(c), '0 == 1')
        c = self.c(operator='not like')
        self.assertEqual(str(c), 'NOT 0 like 1')
        c = self.c(operator='bool')
        self.assertEqual(str(c), '0 bool')

    def test_negate(self):
        c = self.c()
        self.assertIs(c.negated, False)
        c.negate()
        self.assertIs(c.negated, True)
        c.negate()
        self.assertIs(c.negated, False)

    def _eval(self, true, false, **kwargs):
        ct = self.c(**kwargs)
        cf = self.c(negated=True, **kwargs)
        for x in true:
            self.assertTrue(ct.evaluate(*x))
            self.assertFalse(cf.evaluate(*x))
        for x in false:
            self.assertFalse(ct.evaluate(*x))
            self.assertTrue(cf.evaluate(*x))

    def test_eval_eq(self):
        self._eval(true=((2, 2), (4.5, 4.5)), false=((2, 3), (4, 3), (4.5, 4.4)))

    def test_eval_regex(self):
        true = (('abc',), ('abcx',), ('def',), ('defq',))
        false = (('xabc',), ('random',), ('qdef',))
        self._eval(true, false, right=Function('regex', ('abc|def',)), operator='re')

    def test_eval_lt(self):
        d1 = datetime.date(2014, 1, 1)
        d2 = datetime.date(2014, 1, 1)
        d3 = datetime.date(2014, 2, 1)
        true = ((2, 3), (-2.4, -2.1), (d1, d3))
        false = ((3, 2), (3, 3), (-2.1, -2.4), (d3, d1), (d1, d2))
        self._eval(true, false, operator='<')

    def test_eval_lte(self):
        d1 = datetime.date(2014, 1, 1)
        d2 = datetime.date(2014, 1, 1)
        d3 = datetime.date(2014, 2, 1)
        true = ((2, 3), (-2.4, -2.1), (d1, d3), (3, 3), (d1, d2))
        false = ((3, 2), (-2.1, -2.4), (d3, d1))
        self._eval(true, false, operator='<=')

    def test_eval_in(self):
        right = Selector(('const', {2, 4.5, datetime.date(2014, 1, 1), 'hello'}), None)
        true = ((2,), (4.5,), (datetime.date(2014, 1, 1),), ('hello',))
        false = (('2',), ('goodbye',), (datetime.datetime(2014, 1, 1),))
        self._eval(true, false, right=right, operator='in')

    def test_eval_bool(self):
        self.defaults = {'right': None, 'operator': 'bool'}
        true = ((True,), ([1],), (1,), (datetime.date.today(),))
        false = ((None,), (False,), ([],))
        self._eval(true, false)
        f = DeferredDict({'app_label': Selector(0, None)})
        chain = ('objects', ('filter', f))
        l = Selector(('model', 'contenttypes.contenttype'), chain)
        self._eval((('contenttypes',),), (('random',),), left=l)

    def test_eval_error(self):
        self.defaults = {'left': Selector(0, ('hello',))}
        c = self.c()
        self.assertIs(c.evaluate(2, 2), False)
        c.negate()
        self.assertIs(c.evaluate(2, 2), False)
        c = self.c(right=None, operator='bool')
        self.assertIs(c.evaluate(3), False)
        c.negate()
        self.assertIs(c.evaluate(3), True)
        c.negate()
        c.hello = 'goodbye'
        self.assertIs(c.evaluate(c), True)


class TestConditionNode(TestCase):
    def test_init(self):
        n = ConditionNode()
        self.assertEqual(n.children, [])
        self.assertIs(n.negated, False)
        self.assertEqual(n.connector, AND)
        child = Dummy(False)
        n2 = ConditionNode([child], OR, True)
        self.assertEqual(n2.children, [child])
        self.assertIs(n2.negated, True)
        self.assertEqual(n2.connector, OR)

    def test_add_first(self):
        # Not a function I wrote, but I need to make sure they don't change how it works.
        n = ConditionNode()
        child = Dummy(True)
        n.add(child, OR)
        self.assertEqual(n.children, [child])
        self.assertEqual(n.connector, OR)
        # same thing again should do nothing...
        n.add(child, OR)
        self.assertEqual(n.children, [child])
        self.assertEqual(n.connector, OR)
        # even with different connector
        n.add(child, AND)
        self.assertEqual(n.children, [child])
        self.assertEqual(n.connector, AND)

    def test_add_third(self):
        c1, c2, c3 = Dummy(True), Dummy(True), Dummy(False)
        n = ConditionNode([c1, c2])
        n.add(c3, AND)
        self.assertEqual(n.children, [c1, c2, c3])
        self.assertEqual(n.connector, AND)
        # but when you change the connector...
        c4 = Dummy(False)
        n.add(c4, OR)
        self.assertEqual(len(n), 2)
        self.assertEqual(n.connector, OR)
        self.assertIs(n.children[1], c4)
        self.assertEqual(n.children[0].children, [c1, c2, c3])
        self.assertEqual(n.children[0].connector, AND)

    def test_add_node_many_children(self):
        c1, c2, c3 = Dummy(True), Dummy(True), Dummy(False)
        n1 = ConditionNode([c3])
        n2 = ConditionNode([c1, c2], OR)
        n1.add(n2, AND)
        self.assertEqual(n1.children, [c3, n2])
        self.assertEqual(n1.connector, AND)
        n3 = ConditionNode([c3])
        n3.add(n2, OR)
        self.assertEqual(n3.children, [c3, c1, c2])
        self.assertEqual(n3.connector, OR)

    def test_add_node_one_child(self):
        c1, c2 = Dummy(True), Dummy(True)
        n1 = ConditionNode([c2])
        n2 = ConditionNode([c1], OR)
        n1.add(n2, AND)
        self.assertEqual(n1.children, [c2, c1])
        self.assertEqual(n1.connector, AND)
        n3 = ConditionNode([c2])
        n3.add(n2, OR)
        self.assertEqual(n3.children, [c2, c1])
        self.assertEqual(n3.connector, OR)

    def test_add_node_no_children(self):
        c1 = Dummy(True)
        n1 = ConditionNode([c1])
        n2 = ConditionNode([], OR)
        n1.add(n2, AND)
        self.assertEqual(n1.children, [c1, n2])
        self.assertEqual(n1.connector, AND)
        n3 = ConditionNode([c1])
        n3.add(n2, OR)
        self.assertEqual(n3.children, [c1])
        self.assertEqual(n3.connector, OR)

    def test_evaluate(self):
        n1 = ConditionNode()
        self.assertIs(n1.evaluate(), True)
        n1.connector = OR
        self.assertIs(n1.evaluate(), False)
        n2 = ConditionNode([Dummy(True)])
        self.assertIs(n2.evaluate(), True)
        n2.connector = OR
        self.assertIs(n2.evaluate(), True)
        n3 = ConditionNode([Dummy(False)])
        self.assertIs(n3.evaluate(), False)
        n3.connector = OR
        self.assertIs(n3.evaluate(), False)
        n4 = ConditionNode([Dummy(True), Dummy(False)])
        self.assertIs(n4.evaluate(), False)
        n4.connector = OR
        self.assertIs(n4.evaluate(), True)
        n5 = ConditionNode([Dummy(False), Dummy(True)])
        self.assertIs(n5.evaluate(), False)
        n5.connector = OR
        self.assertIs(n5.evaluate(), True)

    def test_negate(self):
        c1, c2 = Dummy(True), Dummy(False)
        n = ConditionNode([c1, c2])
        result = n.evaluate()
        n.negate()
        self.assertEqual(len(n), 1)
        self.assertEqual(n.connector, AND)
        self.assertEqual(n.children[0].children, [c1, c2])
        self.assertEqual(n.children[0].connector, OR)
        # We went from (c1 AND c2) to (!c1 or !c2)
        self.assertEqual(n.evaluate(), not result)
        self.assertIs(c1.v, False)
        self.assertIs(c2.v, True)
        n.negate()
        self.assertIs(c1.v, True)
        self.assertIs(c2.v, False)
        self.assertEqual(len(n), 1)
        self.assertEqual(n.connector, AND)
        self.assertEqual(len(n.children[0]), 1)
        # collapsing at this point should give us back the original node structure
        n.collapse()
        self.assertEqual(n.evaluate(), result)
        self.assertEqual(n.children, [c1, c2])
        self.assertEqual(n.connector, AND)


    def test_collapse(self):
        c1, c2 = Dummy(True), Dummy(True)
        n2, n3 = ConditionNode(), ConditionNode(connector=OR)
        n4, n5 = ConditionNode([c1]), ConditionNode([c2], OR)
        n6, n7 = ConditionNode([c1, c1]), ConditionNode([c2, c2], OR)
        n1 = ConditionNode([n2, n3, n4, n5, n6, n7], OR)
        n1.collapse()
        self.assertEqual(n1.connector, OR)
        self.assertEqual(n1.children, [n6, c1, c2, c2, c2])
        # Now test the recursion of the last part
        n8 = ConditionNode([c1, c2, c1], OR)
        n9 = ConditionNode([ConditionNode([ConditionNode([n8])], OR)])
        self.assertEqual(n9.connector, AND)
        n9.collapse()
        self.assertEqual(n9.connector, OR)
        self.assertEqual(n9.children, [c1, c2, c1])

    def test_invert(self):
        c1, c2 = Dummy(True), Dummy(False)
        n1 = ConditionNode([c1, c2])
        n2 = ~n1
        # Get rid of the extra node added by negation.
        n2.collapse()
        self.assertIsNot(n1, n2)
        self.assertIsNot(n1.children[0], n2.children[0])
        self.assertIsNot(n1.children[1], n2.children[1])
        self.assertNotEqual(n1.connector, n2.connector)
        self.assertEqual(n1.evaluate(), not n2.evaluate())

    def test_iand(self):
        c1, c2 = Dummy(True), Dummy(False)
        n = n1 = ConditionNode([c1, c2])
        n2 = ConditionNode([c1])
        n1 &= n2
        self.assertIs(n, n1)
        self.assertEqual(n.connector, AND)
        self.assertEqual(n.children, [c1, c2, c1])

        n = n1 = ConditionNode([c1], OR)
        n2 = ConditionNode([c1, c2], OR)
        n1 &= n2
        self.assertIs(n, n1)
        self.assertEqual(n.connector, AND)
        self.assertEqual(n.children, [c1, n2])
        # Uses add(); as we've already tested that function, we'll call this sufficient.

    def test_and(self):
        c1, c2 = Dummy(True), Dummy(False)
        n = ConditionNode([c1, c2])
        n2 = ConditionNode([c1])
        n1 = n & n2
        self.assertIsNot(n, n1)
        self.assertEqual(n1.connector, AND)
        vals = [c.v for c in n1.children]
        self.assertEqual(vals, [c1.v, c2.v, c1.v])
        # Uses __iand__, so this test is sufficient, along with test_iand.

    def test_ior(self):
        c1, c2 = Dummy(True), Dummy(False)
        n = n1 = ConditionNode([c1, c2], OR)
        n2 = ConditionNode([c1])
        n1 |= n2
        self.assertIs(n, n1)
        self.assertEqual(n.connector, OR)
        self.assertEqual(n.children, [c1, c2, c1])

        n = n1 = ConditionNode([c1])
        n2 = ConditionNode([c1, c2])
        n1 |= n2
        self.assertIs(n, n1)
        self.assertEqual(n.connector, OR)
        self.assertEqual(n.children, [c1, n2])
        # Uses add(); as we've already tested that function, we'll call this sufficient.

    def test_or(self):
        c1, c2 = Dummy(True), Dummy(False)
        n = ConditionNode([c1, c2], OR)
        n2 = ConditionNode([c1])
        n1 = n | n2
        self.assertIsNot(n, n1)
        self.assertEqual(n1.connector, OR)
        vals = [c.v for c in n1.children]
        self.assertEqual(vals, [c1.v, c2.v, c1.v])
        # Uses __ior__, so this test is sufficient, along with test_ior.


@store.register
def cont1(rule, info, value):
    rule.cont1 = value
    info['value'] = value


@store.register
def cont2(*args):
    raise ValueError


class TestRule(TestCase):
    def test_init_minimum(self):
        self.assertRaises(TypeError, Rule)
        r = Rule(trigger='hello')
        self.assertEqual(r.trigger, 'hello')
        self.assertIs(r.value, None)
        self.assertEqual(r.conditions.connector, OR)
        self.assertEqual(r.conditions.children, [])
        self.assertIs(r.continuation, None)
        self.assertFalse(hasattr(r, 'weight'))

    def test_init(self):
        c1, c2 = Dummy(True), Dummy(False)
        n = ConditionNode([c1, c2])
        r = Rule(trigger='hey', value=4.5, conditions=n, continuation='noop',
                 weight=-5, extraneous='argh')
        self.assertEqual(r.trigger, 'hey')
        self.assertEqual(r.value, 4.5)
        self.assertIs(r.conditions, n)
        self.assertEqual(r.continuation, 'noop')
        self.assertEqual(r.weight, -5)
        self.assertFalse(hasattr(r, 'extraneous'))

    def test_match(self):
        r1 = Rule(trigger='hi')
        self.assertFalse(r1.match())
        def x(q): raise Exception
        r1.conditions = x
        self.assertFalse(r1.match())
        x._evaluate = x
        self.assertIs(r1.conditions._evaluate, x)
        self.assertFalse(r1.match())

        c1, c2 = Dummy(True), Dummy(True)
        n = ConditionNode([c1, c2])
        r2 = Rule(trigger='hi', conditions=n)
        self.assertIs(r2.match(), r2)

    def test_continue_simple(self):
        r1 = Rule('hi', continuation='cont1', value=14)
        i = {}
        r1.continue_(i, store)
        self.assertEqual(i['value'], r1.cont1)

        r2 = Rule('hi', continuation='none')
        self.assertRaises(KeyError, r2.continue_, i, store)
        self.assertRaises(TypeError, r2.continue_, i, None)

    def test_continue_raises(self):
        r = Rule('hi', continuation='cont2')
        self.assertRaises(ValueError, r.continue_, {}, store)

    def test_continue_deferred(self):
        s = Selector(0, ('strip', 2))
        i = {'objects': [' help']}
        r = Rule('hi', continuation='cont1', value=s)
        r.continue_(i, store)
        self.assertEqual(len(i), 3)
        self.assertEqual(i['value'], 'l')
        self.assertEqual(i[id(s)], 'l')
        self.assertEqual(r.cont1, 'l')
        self.assertIs(r.value, s)

    def test_build_tree(self):
        r = Rule('hey')
        c = ConditionNode([Dummy(True)])
        self.assertIs(r._build_tree(c), c)
        x = lambda: None
        x._evaluate = x
        self.assertIs(r._build_tree(x), x)
        # Tested None indirectly in the constructor
        y = r._build_tree('')
        self.assertEqual(y.connector, OR)
        self.assertEqual(y.children, [])
        self.assertTrue(isinstance(y, ConditionNode))

    # TODO once parsing is implemented, need to test _build_tree properly
