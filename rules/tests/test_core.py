from django.contrib.contenttypes.models import ContentType
from django.core.exceptions import FieldError
from django.db import models
from django.test import TestCase
from django.test.utils import override_settings
from model_mommy import mommy
from madlibs.test_utils import CollectMixin

from rules.core import AND, OR, get_value, ConditionNode, Condition


class Object(models.Model):
    str1 = models.CharField(max_length=100, blank=True, null=True)
    str2 = models.CharField(max_length=100, blank=True, null=True)
    bool = models.NullBooleanField()
    int = models.IntegerField(blank=True, null=True)
    float = models.FloatField(blank=True, null=True)
    decimal = models.DecimalField(decimal_places=10, max_digits=20, blank=True, null=True)

    class Meta:
        app_label = 'rules'

class Base(CollectMixin, TestCase):
    def prep(self, **kwargs):
        kwargs = self._collect('kwargs', kwargs)
        return mommy.prepare(Object, **kwargs)

    def make(self, **kwargs):
        kwargs = self._collect('kwargs', kwargs)
        return mommy.make(Object, **kwargs)

    def c(self, **kwargs):
        return Condition(**self._collect('defaults', kwargs))

    def C(self, *args, **kwargs):
        return Condition.C(*args, **kwargs)


class TestGetValue(Base):
    def test_simple(self):
        c = ['str1', 'str2']
        o = self.prep(str1='1', str2='2')
        self.assertEqual(get_value(o, c, i=1), '2')
        self.assertEqual(get_value(o, c[:1]), '1')

    def test_dict_chain(self):
        c = ['str1', 'str2']
        o = {'str1': '1', 'str2': '2'}
        self.assertEqual(get_value(o, c, i=1), '2')
        self.assertEqual(get_value(o, c[:1]), '1')

    def test_length(self):
        c = []
        self.assertIs(get_value(c, c, i=0), c)
        self.assertIs(get_value(c, c, i=1), c)

    def test_callable(self):
        c = ['objects', 'get']
        o = self.make()
        self.assertEqual(get_value(Object, c).pk, o.pk)

    def test_skip(self):
        c = ['', 'objects', '', 'get']
        o = self.make()
        self.assertEqual(get_value(Object, c).pk, o.pk)

    def test_nonexistent(self):
        c = ['str1', 'strip', 'ugabuga', 'hello']
        o = self.prep()
        self.assertIs(get_value(o, c), None)


class TestCondition(Base):
    def test_neg_op_map(self):
        nom = {'!=': '==', 'not like': 're', 'not in': 'in',
               '>=': '<', 'does not exist': 'bool', '>': '<='}
        self.assertEqual(Condition.NEGATED_OPERATOR_MAP, nom)

    def test_op_map(self):
        om = {'!=': '==', '==': '==', 'like': 're', 'not like': 're', 'not in': 'in',
              'in': 'in', '>=': '<', '<=': '<=', 'does not exist': 'bool', '>': '<=',
              'exists': 'bool', '<': '<'}
        self.assertEqual(Condition.OPERATOR_MAP, om)

    def test_kwargs(self):
        kwargs = set(('left', 'right', 'value', 'negated', 'operator'))
        self.assertEqual(set(Condition.KWARGS), kwargs)

    def test_kwarg_op_map(self):
        kom = {'lt': '<', 'lte': '<=', 'gt': '>', 'gte': '>=',
               'exists': 'bool', 'like': 're', 'in': 'in'}
        self.assertEqual(Condition.KWARG_OP_MAP, kom)

    def test_parse_kwarg(self):
        v = complex(4, 5)
        key = 'o234__gg'
        result = {'left': '234.gg', 'right': 'const', 'value': v, 'operator': '=='}
        self.assertEqual(Condition.parse_kwarg(key, v), result)
        key = 'hello__gg'
        result['left'] = 'extra.hello.gg'
        self.assertEqual(Condition.parse_kwarg(key, v), result)
        # Unrecognized operator...
        key = 'hello__gg__not_exists'
        result['operator'] = '=='
        result['left'] = 'extra.hello.gg.not_exists'
        self.assertEqual(Condition.parse_kwarg(key, v), result)
        key = 'hello__gg__exists'
        result = {'operator': 'bool', 'left': 'extra.hello.gg', 'negated': not v}
        self.assertEqual(Condition.parse_kwarg(key, v), result)


class TestGetMod(Base):
    defaults = {'left': 'model.rules.object', 'operator': 'bool'}
    kwargs = {'str1': 'hello', 'int': 5}

    def test_bad_field(self):
        c = self.c()
        self.assertRaises(TypeError, c._get_mod, ('skgjfks',), {})

    def test_bad_ct(self):
        c = self.c()
        self.assertRaises(ContentType.DoesNotExist, c._get_mod, ('fake', 'model'), {})

    def test_no_filters(self):
        o = self.make()
        c = self.c()
        qs = c._get_mod(('rules', 'object'), None)
        self.assertEqual(len(qs), 1)
        self.assertEqual(qs[0].pk, o.pk)

    def test_bad_filters(self):
        c = self.c(value={'nofield': False})
        # extra has to be a dict
        self.assertRaises(TypeError, c._get_mod, ('rules', 'object'), None)
        self.assertRaises(FieldError, c._get_mod, ('rules', 'object'), {})

    def test_filters_applied(self):
        o = self.make()
        c = self.c(value={'str1__isnull': False})
        self.assertEqual(len(c._get_mod(('rules', 'object'), {})), 1)
        c.value['str1__isnull'] = True
        self.assertEqual(len(c._get_mod(('rules', 'object'), {})), 0)

    def test_extra_override(self):
        o = self.make()
        c = self.c(value={'str1__isnull': False})
        self.assertEqual(len(c._get_mod(('rules', 'object'), {})), 1)
        self.assertEqual(len(c._get_mod(('rules', 'object'), {'str1__isnull': True})), 0)


class Dummy(object):
    def __init__(self, value):
        self.v = value

    def negate(self):
        self.v = not self.v

    def _evaluate(self, objects, extra):
        return self.v

    def __str__(self):
        return str(id(self))


class TestConditionNode(Base):
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
        # unless the connector is different
        n.add(child, AND)
        self.assertEqual(n.children, [child, child])
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
