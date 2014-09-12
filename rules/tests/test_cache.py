from unittest import SkipTest
from django.test import TestCase

from rules.cache import *
from rules.conf import settings
from rules.core import ConditionNode
from . import Dummy

if settings.RULES_CONCRETE_MODELS:
    from rules.models import Rule, expand_model_key
else:
    from rules.models import BaseRule, expand_model_key

    class Rule(BaseRule):
        class Meta:
            app_label = 'rules'

    RuleCache.default = RuleCache(Rule.objects)
    TopicalRuleCache.default = TopicalRuleCache(RuleCache.default, [expand_model_key])

    del BaseRule


class TestExpandModelKey(TestCase):
    def test_bad(self):
        self.assertIs(expand_model_key('hello.rules.rule'), NotImplemented)
        self.assertIs(expand_model_key('create.rules'), NotImplemented)
        self.assertIs(expand_model_key('create.rules.rule.'), NotImplemented)
        self.assertRaises(ValueError, expand_model_key, 'create.rules.rule:post_delete')
        self.assertRaises(ValueError, expand_model_key, 'create.rules.rule:pre_delete')
        self.assertRaises(ValueError, expand_model_key, 'update.rules.rule:post_delete')
        self.assertRaises(ValueError, expand_model_key, 'update.rules.rule:pre_delete')
        self.assertRaises(ValueError, expand_model_key, 'delete.rules.rule:post_save')
        self.assertRaises(ValueError, expand_model_key, 'delete.rules.rule:pre_save')
        self.assertRaises(ValueError, expand_model_key, 'create.rules.rule:post_random')
        self.assertRaises(ValueError, expand_model_key, 'create.rules.rule:random')

    def test_create(self):
        key = 'create.rules.rule'
        x = expand_model_key(key)
        expected = {'#', 'create.#', 'create.rules.#', '#.rules.#', '#.rules.rule', key}
        self.assertEqual(set(x), expected)

    def test_update(self):
        key = 'update.rules.rule'
        x = expand_model_key(key)
        expected = {'#', 'update.#', 'update.rules.#', '#.rules.#', '#.rules.rule', key}
        self.assertEqual(set(x), expected)

    def test_delete(self):
        key = 'delete.rules.rule'
        x = expand_model_key(key)
        expected = {'#', 'delete.#', 'delete.rules.#', '#.rules.#', '#.rules.rule', key}
        self.assertEqual(set(x), expected)

    def test_signals(self):
        key = 'create.rules.rule'
        post = {'#', 'create.#', 'create.rules.#', '#.rules.#', '#.rules.rule', key}
        self.assertEqual(set(expand_model_key(key + ':post_save')), post)
        key += ':pre_save'
        pre = {'#:pre_save', 'create.#:pre_save', 'create.rules.#:pre_save',
               '#.rules.#:pre_save', '#.rules.rule:pre_save', key}
        self.assertEqual(set(expand_model_key(key)), pre)
        key = key.replace('save', 'delete')
        pre = {x.replace('save', 'delete') for x in pre}


class TestExpandKey(TestCase):
    def test1(self):
        key = 'hello'
        expected = {'#', key, 'hello.#'}
        self.assertEqual(set(expand_key(key)), expected)

    def test2(self):
        key = 'hello.goodbye'
        expected = {'#', key, 'hello.goodbye.#', 'hello.#'}
        self.assertEqual(set(expand_key(key)), expected)

    def test3(self):
        key = 'hello.2345.#:%^'
        expected = {'#', key, 'hello.#', 'hello.2345.#', 'hello.2345.#:%^.#'}
        self.assertEqual(set(expand_key(key)), expected)


TRUE = ConditionNode()


class TestCollectionBase(TestCase):
    __test__ = False

    def setUp(self):
        x = lambda y: TRUE if y%2 else None
        r = []
        for i in range(7):
            weight = -i if i%3 else i
            rule = Rule(weight=weight, trigger='hello')
            rule.save()
            rule.conditions = x(i)
            r.append(rule)
        self.rules = r

    def test_init(self):
        if not hasattr(self, 'cls'):
            raise SkipTest
        r = self.cls(self.rules)
        self.assertEqual(len(r), len(self.rules))
        s = tuple(sorted(self.rules, key=lambda x: x.weight))
        self.assertNotEqual(tuple(r), tuple(self.rules))
        self.assertEqual(set(r), set(self.rules))
        s = tuple(sorted(self.rules, key=lambda x: x.weight))
        self.assertEqual(tuple(r), s)


class TestRuleList(TestCollectionBase):
    cls = RuleList
    __test__ = True

    def test_matches(self):
        r = RuleList(self.rules)
        m = r.matches()
        self.assertEqual(len(m), 3)
        for x in m:
            self.assertIn(x, r)
            self.assertTrue(x.match())
        for y in set(r) - set(m):
            self.assertNotIn(y, m)
            self.assertFalse(y.match())


class TestRuleMutex(TestCollectionBase):
    cls = RuleMutex
    __test__ = True

    def test_weight(self):
        r = self.cls(self.rules)
        self.assertEqual(r.weight, min(*(x.weight for x in self.rules)))
        y = [z for z in self.rules if z.weight > -4]
        r = self.cls(y)
        self.assertEqual(r.weight, min(*(x.weight for x in y)))

    def test_match1(self):
        r = self.cls(self.rules)
        x = r.match()
        self.assertTrue(x.match())
        self.assertIn(x, r)
        m = RuleList(self.rules).matches()
        self.assertIs(m[0], x)

    def test_match2(self):
        r = self.cls(filter(lambda z: z.weight > -4, self.rules))
        self.assertEqual(len(r), 5)
        x = self.cls(self.rules).match()
        y = r.match()
        self.assertIsNot(x, y)
        m = RuleList(r).matches()
        self.assertIs(m[0], y)

    def test_match3(self):
        r = self.cls(filter(lambda z: not z.match(), self.rules))
        self.assertEqual(len(r), 4)
        self.assertFalse(r.match())


class TestRuleCache(TestCase):
    def setUp(self):
        for i in range(3):
            Rule.objects.create(weight=i, trigger='hello')
        Rule.objects.create(trigger='goodbye')

    def test_init(self):
        r = RuleCache(3)
        self.assertEqual(r.source, 3)
        self.assertTrue(isinstance(r.sources, dict))
        self.assertEqual(len(r.sources), 0)
        self.assertEqual(len(r), 0)

    def test_default_source1(self):
        r = RuleCache(Rule.objects)
        x = r.get_default_source('hello')
        self.assertTrue(callable(x))
        self.assertRaises(TypeError, x)
        y = x(r)
        self.assertEqual(len(y), 3)
        self.assertEqual({z.trigger for z in y}, {'hello'})
        w = x(None)
        self.assertEqual(tuple(y), tuple(w))
        r.source = None
        self.assertRaises(AttributeError, x, r)

    def test_default_source2(self):
        r = RuleCache(Rule.objects)
        x = r.get_default_source('goodbye')
        y = x(None)
        self.assertEqual(len(y), 1)
        self.assertEqual(y[0].trigger, 'goodbye')

    def test_default_source3(self):
        r = RuleCache(Rule.objects)
        x = r.get_default_source('random')
        self.assertFalse(x(None))

    def test_sources(self):
        r = RuleCache(Rule.objects)
        self.assertNotIn('hello', r.sources)
        x = r.sources['hello']
        self.assertIn('hello', r.sources)
        self.assertEqual(len(x), 1)
        y = x[0](None)
        z = r.get_default_source('hello')(None)
        self.assertEqual(tuple(y), tuple(z))
        self.assertEqual(len(y), 3)

    def test_set_primary_source(self):
        r = RuleCache(Rule.objects)
        self.assertNotIn('goodbye', r.sources)
        r.set_primary_source('goodbye', lambda c: set(c.source.all()))
        self.assertEqual(len(r.sources['goodbye']), 1)
        x = r.sources['goodbye'][0](r)
        y = r.get_default_source('goodbye')(r)
        self.assertEqual(len(x), 4)
        self.assertEqual(len(y), 1)
        self.assertTrue(isinstance(x, set))
        self.assertEqual(x, set(Rule.objects.all()))
        self.assertRaises(AttributeError, r.sources['goodbye'][0], None)

    def test_add_source(self):
        d = Dummy(True)
        r = RuleCache(Rule.objects)
        self.assertNotIn('hello', r.sources)
        r.add_source('hello', d)
        self.assertEqual(len(r.sources['hello']), 2)
        primary, added = r.sources['hello']
        self.assertEqual(tuple(primary(0)), tuple(r.get_default_source('hello')(0)))
        self.assertIs(added, d)

    def test_setitem_single(self):
        r = RuleCache(None)
        r['random'] = d = Dummy(True)
        self.assertEqual(len(r), 1)
        # Setting an item doesn't look at sources.
        self.assertNotIn('random', r.sources)
        x = r['random']
        self.assertNotIn('random', r.sources)
        self.assertTrue(isinstance(x, RuleList))
        self.assertEqual(len(x), 1)
        self.assertIs(x[0], d)

    def test_setitem_with_matches(self):
        r = RuleCache(None)
        obj = Exception()
        # As long as it has a _matches attr, the cache thinks it's valid.
        obj._matches = 'placeholder'
        r['funny'] = obj
        self.assertIs(r['funny'], obj)

    def test_setitem_iterable(self):
        r = RuleCache(None)
        d = [Dummy(True)]
        r['me'] = d
        self.assertIsNot(r['me'], d)
        self.assertTrue(isinstance(r['me'], RuleList))
        self.assertEqual(tuple(r['me']), tuple(d))

    def test_missing_default_source(self):
        r = RuleCache(Rule.objects)
        self.assertNotIn('hello', r)
        self.assertNotIn('hello', r.sources)
        x = r['hello']
        self.assertIn('hello', r)
        self.assertIn('hello', r.sources)
        self.assertEqual(x, RuleList(Rule.objects.filter(trigger='hello')))

    def test_missing_custom_source(self):
        r = RuleCache(Rule.objects.all())
        r.set_primary_source('mixed', lambda c: (q for q in c.source if q.pk % 2))
        self.assertNotIn('mixed', r)
        self.assertIn('mixed', r.sources)
        x = r['mixed']
        self.assertEqual(len(x), 2)
        self.assertEqual(x[0].pk % 2, 1)
        self.assertEqual(x[1].pk % 2, 1)

    def test_missing_added_source(self):
        r = RuleCache(Rule.objects.all())
        d0 = Dummy(True, weight=-1)
        d1 = Rule.objects.get(trigger='goodbye')
        d2 = Dummy(True, weight=1)
        # Test object with _match
        r.add_source('goodbye', d2)
        # Test callable and list
        r.add_source('goodbye', lambda c: [d0])
        x = r['goodbye']
        self.assertEqual(len(x), 3)
        self.assertEqual(x, RuleList([d0, d1, d2]))
        r.add_source('you', None)
        # Like __setitem__, thinks source must be an iterable since it doesn't have _match
        with self.assertRaises(TypeError):
            y = r['you']


def _trc(source=None, queryset=Rule.objects, expanders=[expand_model_key]):
    if not source:
        source = RuleCache(queryset)
    return TopicalRuleCache(source, expanders)


def custexpander(key):
    parts = key.split('.')
    if '42' in parts:
        return ('life', 'universe', 'everything')
    return NotImplemented


class TestTopicalRuleCache(TestCase):
    def setUp(self):
        for i in range(3):
            Rule.objects.create(weight=i, trigger='hello')
        Rule.objects.create(trigger='#')

    def test_init(self):
        r = TopicalRuleCache(3)
        self.assertEqual(r.source, 3)
        self.assertTrue(isinstance(r.sources, dict))
        self.assertEqual(len(r.sources), 0)
        self.assertEqual(len(r), 0)
        self.assertEqual(r.expanders, [])
        r = _trc(expanders=4)
        self.assertEqual(r.expanders, 4)

    def test_expandkey_default(self):
        r = TopicalRuleCache(None)
        key1 = 'create.rules.rule'
        expected = {'#', key1, 'create.#', 'create.rules.#', 'create.rules.rule.#'}
        self.assertEqual(set(r._expandkey(key1)), expected)
        key2 = 'must.see42'
        expected = {'#', key2, 'must.#', 'must.see42.#'}
        self.assertEqual(set(r._expandkey(key2)), expected)
        key3 = 'update.42'
        expected = {'#', key3, 'update.#', 'update.42.#'}
        self.assertEqual(set(r._expandkey(key3)), expected)

    def test_expandkey_model_then_custom(self):
        r = TopicalRuleCache(None, expanders=[expand_model_key, custexpander])
        key1 = 'create.rules.rule'
        expected = {'#', key1, 'create.#', 'create.rules.#', '#.rules.#', '#.rules.rule'}
        self.assertEqual(set(r._expandkey(key1)), expected)
        key2 = 'must.see42'
        expected = {'#', key2, 'must.#', 'must.see42.#'}
        self.assertEqual(set(r._expandkey(key2)), expected)
        key3 = 'update.42.one'
        expected = {'#', key3, 'update.#', 'update.42.#', '#.42.#', '#.42.one'}
        self.assertEqual(set(r._expandkey(key3)), expected)

    def test_expandkey_custom_then_model(self):
        r = TopicalRuleCache(None, expanders=[custexpander, expand_model_key])
        key1 = 'create.rules.rule'
        expected = {'#', key1, 'create.#', 'create.rules.#', '#.rules.#', '#.rules.rule'}
        self.assertEqual(set(r._expandkey(key1)), expected)
        key2 = 'must.see42'
        expected = {'#', key2, 'must.#', 'must.see42.#'}
        self.assertEqual(set(r._expandkey(key2)), expected)
        key3 = 'update.42.one'
        self.assertEqual(r._expandkey(key3), ('life', 'universe', 'everything'))

    def test_default_source1(self):
        r = _trc()
        s = r.get_default_source('hello')
        x = s(None)
        self.assertEqual(len(x), 4)
        self.assertEqual(len(r), 0)
        self.assertEqual(len(r.source), 3)

    def test_default_source2(self):
        r = _trc(expanders=[custexpander])
        s = r.get_default_source('42')
        x = s(None)
        self.assertEqual(len(x), 0)
        self.assertEqual(len(r), 0)
        self.assertEqual(len(r.source), 3)

    def test_default_source3(self):
        r = _trc()
        s = r.get_default_source('create.rules.rule')
        x = s(None)
        self.assertEqual(len(x), 1)
        self.assertEqual(len(r), 0)
        self.assertEqual(len(r.source), 6)

    def test_clear(self):
        r = _trc()
        x = r['hello']
        self.assertEqual(len(r), 1)
        self.assertEqual(len(r.source), 3)
        r.clear()
        self.assertEqual(len(r), 0)
        self.assertEqual(len(r.source), 0)

    def test_delitem(self):
        r = _trc()
        x = r['hello']
        y = r['goodbye']
        self.assertEqual(len(r), 2)
        self.assertEqual(set(r.source), {'#', 'hello', 'hello.#', 'goodbye', 'goodbye.#'})
        del r['hello']
        self.assertEqual(len(r), 1)
        self.assertEqual(set(r.source), {'goodbye', 'goodbye.#'})
        z = r['goodbye']
        self.assertEqual(set(r.source), {'goodbye', 'goodbye.#'})
        w = r['you']
        self.assertEqual(set(r.source), {'#', 'you', 'you.#', 'goodbye', 'goodbye.#'})
