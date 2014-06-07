import copy
import datetime
from decimal import Decimal

from django.core.exceptions import FieldError, ValidationError
from django.contrib.contenttypes.models import ContentType
from django.db import models
from django.test import TestCase
from django.utils import timezone
from model_mommy import mommy
from madlibs.models.fields import JSONTextField

from rule_reactor.matchers import *
# To make things simpler we'll test against condition instances.
from rule_reactor.models import Condition


class Object(models.Model):
    str1 = models.CharField(max_length=100, blank=True, null=True)
    str2 = models.CharField(max_length=100, blank=True, null=True)
    bool = models.NullBooleanField()
    int = models.IntegerField(blank=True, null=True)
    float = models.FloatField(blank=True, null=True)
    decimal = models.DecimalField(decimal_places=10, max_digits=20, blank=True, null=True)
    json = JSONTextField(blank=True, null=True)

    class Meta:
        app_label = 'rule_reactor'


class Base(TestCase):
    def setUp(self):
        self.ct = ContentType.objects.get_for_model(Object)

    def _combine(self, into, kwargs):
        for key, val in kwargs.items():
            if isinstance(val, dict) and key in into:
                self._combine(into[key], val)
            else:
                into[key] = val

    def _collect_kwargs(self, kwargs, key='defaults'):
        _kwargs = {}
        for base in self.revmro() + [self]:
            if key in base.__dict__:
                self._combine(_kwargs, base.__dict__[key])
        self._combine(_kwargs, kwargs)
        return _kwargs

    @classmethod
    def revmro(cls):
        if '_mro' not in cls.__dict__:
            mro = list(reversed(cls.__mro__))
            cls._mro = mro[mro.index(Base):]
        return cls._mro

    def make(self, **kwargs):
        kwargs = self._collect_kwargs(kwargs)
        kwargs.setdefault('rule__table', self.ct)
        if kwargs.get('apply_to') == 'mod':
            kwargs.setdefault('field', '{0.app_label}.{0.model}'.format(kwargs['rule__table']))
        return mommy.make(Condition, **kwargs)


class TestClean(Base):
    defaults = {'apply_to': 'mod'}

    def test_int(self):
        c = self.make(apply_to='int', field='skfgsdmkgh', value=['ehhlahg'])
        c.full_clean()
        self.assertEqual(c.field, '.')
        self.assertEqual(c.value, '')

    def test_mod(self):
        c = self.make()
        self.assertFalse(c.value)
        self.assertEqual(c.field, 'rule_reactor.object')
        self.assertEqual(c.comparison, 'exists')
        c.full_clean()

    def test_mod_comp(self):
        c = self.make(comparison='equal')
        with self.assertRaises(ValidationError) as ar:
            c.full_clean()
        self.assertEqual(set(ar.exception.message_dict), set(['value']))
        c = self.make(comparison='exists')
        c.full_clean()

    def test_mod_comp_good(self):
        c = self.make(comparison='equal', value={'left_field': '', 'right_field': ''})
        self.assertRaises(ValidationError, c.full_clean)
        c.value['left_field'] = 'ghsdjkl'
        self.assertRaises(ValidationError, c.full_clean)
        c.value['left_field'] = ''
        c.value['right_field'] = 'ghsdjkl'
        self.assertRaises(ValidationError, c.full_clean)
        c.value['left_field'] = 'ghsdjkl'
        c.full_clean()

    def test_mod_value(self):
        c = self.make(value=['hello'])
        with self.assertRaises(ValidationError) as ar:
            c.full_clean()
        self.assertEqual(set(ar.exception.message_dict), set(['value']))
        c = self.make(value={'hello': 'me'})
        c.full_clean()

    def test_mod_field(self):
        c = self.make(field='adhgkd')
        with self.assertRaises(ValidationError) as ar:
            c.full_clean()
        self.assertEqual(set(ar.exception.message_dict), set(['field']))
        ct = ContentType.objects.get_for_model(ContentType)
        c = self.make(field='{}.{}'.format(ct.app_label, ct.model))
        c.full_clean()

    def test_mod_all(self):
        c = self.make(field='adhgkd', value=23534, comparison='lt')
        with self.assertRaises(ValidationError) as ar:
            c.full_clean()
        self.assertEqual(set(ar.exception.message_dict), set(('field', 'value')))


class TestGetMod(Base):
    defaults = {'apply_to': 'mod'}

    def setUp(self):
        super(TestGetMod, self).setUp()
        self.ct = ContentType.objects.get_for_model(Condition)

    def test_bad_field(self):
        c = self.make(field='aslkdghl')
        self.assertRaises(TypeError, c._get_mod, c, {})

    def test_bad_ct(self):
        c = self.make(field='fake.model')
        self.assertRaises(ContentType.DoesNotExist, c._get_mod, c, {})

    def test_no_filters(self):
        c = self.make()
        qs = c._get_mod(None, None)
        self.assertEqual(len(qs), 1)
        self.assertEqual(qs[0].pk, c.pk)

    def test_fields_ignored(self):
        c = self.make(value={'left_field': '', 'right_field': ''})
        qs = c._get_mod(None, None)
        self.assertEqual(len(qs), 1)
        self.assertEqual(qs[0].pk, c.pk)
        c.value['nofield'] = ''
        # since we're at it, we'll test that extra should have __in__ defined
        self.assertRaises(TypeError, c._get_mod, None, None)
        self.assertRaises(FieldError, c._get_mod, None, {})

    def test_filters_applied(self):
        c = self.make(value={'comparison': 'equal'})
        self.assertEqual(len(c._get_mod(None, {})), 0)
        c = self.make(value={'comparison': 'exists'})
        self.assertEqual(len(c._get_mod(None, {})), 2)

    def test_extra_override(self):
        c = self.make(value={'comparison': 'equal'})
        self.assertEqual(len(c._get_mod(None, {})), 0)
        self.assertEqual(len(c._get_mod(None, {'comparison': 'exists', 'random': 'value'})), 1)

    def test_obj_filter(self):
        c1 = self.make(value={'rule': None})
        c2 = self.make()
        self.assertEqual(len(c1._get_mod(None, {})), 0)
        qs = c1._get_mod(c2.rule, {})
        self.assertEqual(len(qs), 1)
        self.assertEqual(qs[0].pk, c2.pk)
        self.assertEqual(len(c2._get_mod(None, {})), 2)

    def test_obj_id_filter(self):
        c1 = self.make(value={'rule_id': None})
        c2 = self.make(value={'rule__pk': None})
        c3 = self.make(value={'pk': None})
        self.assertRaises(AttributeError, c1._get_mod, None, {})
        qs = c1._get_mod(c2.rule, {})
        self.assertEqual(len(qs), 1)
        self.assertEqual(qs[0].pk, c2.pk)
        qs = c2._get_mod(c2.rule, {})
        self.assertEqual(len(qs), 1)
        self.assertEqual(qs[0].pk, c2.pk)
        qs = c3._get_mod(c2, {})
        self.assertEqual(len(qs), 1)
        self.assertEqual(qs[0].pk, c2.pk)


class TestGetValue(Base):
    def test_simple(self):
        c = self.make(field='apply_to')
        self.assertEqual(c._get_value(c), c.apply_to)

    def test_dict(self):
        c = self.make(field='one')
        self.assertEqual(c._get_value({'one': 1}), 1)

    def test_keys(self):
        c = self.make(field='one')
        self.assertEqual(c._get_value({'one': 1, 'two': 2}, keys=['two']), 2)

    def test_length(self):
        c = self.make()
        self.assertIs(c._get_value(c, i=1), c)
        self.assertIs(c._get_value(c, i=2), c)

    def test_callable(self):
        c = self.make(field='objects.get')
        self.assertEqual(c._get_value(Condition).pk, c.pk)

    def test_nonexistent(self):
        c = self.make(field='apply_to.strip.ugabuga.hello')
        self.assertIs(c._get_value(c), None)


class TestTryMatchType(Base):
    def test_compatible(self):
        c = Condition()
        l1, r1 = 'ehllo', 'ogobye'
        l2, r2 = c._try_match_type(l1, r1)
        self.assertIs(l1, l2)
        self.assertIs(r1, r2)

    def test_not_str(self):
        c = Condition()
        l1, r1 = 'ehllo', datetime.date.today()
        l2, r2 = c._try_match_type(l1, r1)
        self.assertIs(l1, l2)
        self.assertIs(r1, r2)

    def test_int(self):
        c = Condition()
        l1, r1 = 5, 'hello'
        l2, r2 = c._try_match_type(l1, r1)
        self.assertIs(l1, l2)
        self.assertIs(r1, r2)
        r1 = '6235.243'
        l2, r2 = c._try_match_type(l1, r1)
        self.assertIs(r1, r2)
        r1 = '6235'
        l2, r2 = c._try_match_type(l1, r1)
        self.assertIs(l1, l2)
        self.assertIsNot(r1, r2)
        self.assertEqual(r2, 6235)

    def test_float(self):
        c = Condition()
        l1, r1 = 5.4, 'hello'
        l2, r2 = c._try_match_type(l1, r1)
        self.assertIs(l1, l2)
        self.assertIs(r1, r2)
        r1 = '62.234'
        l2, r2 = c._try_match_type(l1, r1)
        self.assertIs(l1, l2)
        self.assertIsNot(r1, r2)
        self.assertEqual(r2, 62.234)

    def test_date(self):
        c = Condition()
        l1, r1 = datetime.date.today(), 'hello'
        l2, r2 = c._try_match_type(l1, r1)
        self.assertIs(l1, l2)
        self.assertIs(r1, r2)
        r1 = '1980-05-24'
        l2, r2 = c._try_match_type(l1, r1)
        self.assertIs(l1, l2)
        self.assertIsNot(r1, r2)
        self.assertEqual(r2, datetime.date(1980, 5, 24))

    def test_datetime_naive(self):
        c = Condition()
        l1, r1 = datetime.datetime.now(), 'hello'
        l2, r2 = c._try_match_type(l1, r1)
        self.assertIs(l1, l2)
        self.assertIs(r1, r2)
        r1 = str(l1)
        l2, r2 = c._try_match_type(l1, r1)
        self.assertIs(l1, l2)
        self.assertIsNot(r1, r2)
        self.assertEqual(r2, l1)
        self.assertTrue(timezone.is_naive(l1))
        self.assertTrue(timezone.is_naive(r2))

    def test_datetime_aware(self):
        c = Condition()
        l1, r1 = timezone.now(), 'hello'
        l2, r2 = c._try_match_type(l1, r1)
        self.assertIs(l1, l2)
        self.assertIs(r1, r2)
        r1 = str(l1)
        l2, r2 = c._try_match_type(l1, r1)
        self.assertIs(l1, l2)
        self.assertIsNot(r1, r2)
        self.assertEqual(r2, l1)
        self.assertTrue(timezone.is_aware(l1))
        self.assertTrue(timezone.is_aware(r2))

    def test_datetime_aware_to_naive(self):
        c = Condition()
        l1, r1 = timezone.now(), 'hello'
        l2, r2 = c._try_match_type(l1, r1)
        self.assertIs(l1, l2)
        self.assertIs(r1, r2)
        naive = timezone.make_naive(l1, timezone.get_current_timezone())
        r1 = str(naive)
        l2, r2 = c._try_match_type(l1, r1)
        self.assertIs(l1, l2)
        self.assertIsNot(r1, r2)
        self.assertEqual(r2, l1)
        self.assertRaises(TypeError, self.assertEqual, r2, naive)
        self.assertRaises(TypeError, self.assertEqual, l2, naive)
        self.assertTrue(timezone.is_aware(l1))
        self.assertTrue(timezone.is_aware(r2))

    def test_datetime_naive_to_aware(self):
        c = Condition()
        l1, r1 = datetime.datetime.now(), 'hello'
        l2, r2 = c._try_match_type(l1, r1)
        self.assertIs(l1, l2)
        self.assertIs(r1, r2)
        aware = timezone.make_aware(l1, timezone.get_current_timezone())
        r1 = str(aware)
        l2, r2 = c._try_match_type(l1, r1)
        self.assertIs(l1, l2)
        self.assertIsNot(r1, r2)
        self.assertEqual(r2, l1)
        self.assertRaises(TypeError, self.assertEqual, r2, aware)
        self.assertRaises(TypeError, self.assertEqual, l2, aware)
        self.assertTrue(timezone.is_naive(l1))
        self.assertTrue(timezone.is_naive(r2))


class TestDTWithActiveTimezone(Base):
    test_datetime_naive = TestTryMatchType.__dict__['test_datetime_naive']
    test_datetime_aware = TestTryMatchType.__dict__['test_datetime_aware']
    test_datetime_aware_to_naive = TestTryMatchType.__dict__['test_datetime_aware_to_naive']
    test_datetime_naive_to_aware = TestTryMatchType.__dict__['test_datetime_naive_to_aware']

    def setup(self):
        timezone.activate('America/Denver')

    def tearDown(self):
        timezone.deactivate()
