from django.contrib.contenttypes.models import ContentType
from django.core.exceptions import FieldError
from django.db import models
from django.test import TestCase
from django.test.utils import override_settings
from model_mommy import mommy
from madlibs.test_utils import CollectMixin

from rules.core import get_value, ConditionNode, Condition


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
        key = 'hello__gg__exists'
        result['operator'] = 'bool'
        self.assertEqual(Condition.parse_kwarg(key, v), result)
        # Unrecognized operator...
        key = 'hello__gg__not_exists'
        result['operator'] = '=='
        result['left'] = 'extra.hello.gg.not_exists'
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
