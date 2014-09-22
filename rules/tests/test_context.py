from django.test import TestCase

from rules.cache import RuleCache, TopicalRuleCache, SourcelessCache
from rules.context import RuleChecker, SignalChecker
from rules.continuations import ContinuationStore, store
from rules.conf import settings
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

store = store.copy()
store.clear()


class DifferentRuleCache(RuleCache):
    # Just to test the cls argument
    default = NotImplemented

    def __init__(self, source=None):
        super(DifferentRuleCache, self).__init__(source)


class TestRuleChecker(TestCase):
    def setUp(self):
        self.rule1 = Rule.objects.create(trigger='create.rules.#', weight=1)
        self.rule2 = Rule.objects.create(trigger='#.rules.#')

    def test_init_minimum(self):
        rc = RuleChecker()
        self.assertFalse(hasattr(rc, 'continuations'))
        self.assertIs(rc.cache, TopicalRuleCache.default)
        self.assertIs(rc._cont, ContinuationStore.default)
        self.assertEqual(rc.context, {})

    def test_init_cont(self):
        rc = RuleChecker(continuations=NotImplemented, hello=3, goodbye=4)
        self.assertIs(rc._cont, NotImplemented)
        self.assertEqual(rc.context, {'hello': 3, 'goodbye': 4})
        rc = RuleChecker(life=42, universe=42, everything=42)
        self.assertEqual(rc.context, {'life': 42, 'universe': 42, 'everything': 42})

    def test_init_default(self):
        d1, d2 = TopicalRuleCache.default, RuleCache.default
        del TopicalRuleCache.default
        del RuleCache.default
        self.assertRaises(ValueError, RuleChecker)
        rc = RuleChecker(cls=DifferentRuleCache)
        self.assertIs(rc.cache, NotImplemented)
        TopicalRuleCache.default, RuleCache.default = d1, d2
        # Test precendence; all these keywords have precedence over default (duh)
        d = Dummy(True, trigger='')
        for k in ('cache', 'rules', 'queryset', 'source'):
            rc = RuleChecker(cls=DifferentRuleCache, **{k: RuleCache.default})
            self.assertIsNot(rc.cache, NotImplemented)

    def test_init_cache(self):
        rc = RuleChecker(cache=3)
        self.assertEqual(rc.cache, 3)
        c = RuleCache(None)
        rc = RuleChecker(cache=c)
        self.assertIs(rc.cache, c)

    def test_init_rules(self):
        d1 = Dummy(False, trigger='me', weight=1)
        d2 = Dummy(True, trigger='you')
        d3 = Dummy(True, trigger='me')
        rc = RuleChecker(rules=[d1, d2, d3])
        self.assertTrue(isinstance(rc.cache, TopicalRuleCache))
        self.assertFalse(isinstance(rc.cache.source, RuleCache))
        self.assertEqual(tuple(rc.cache['me']), (d3, d1))
        self.assertEqual(tuple(rc.cache['you']), (d2,))
        rc = RuleChecker(rules=[d1, d2, d3], cls=SourcelessCache)
        self.assertTrue(isinstance(rc.cache, SourcelessCache))
        self.assertEqual(tuple(rc.cache['me']), (d3, d1))
        self.assertEqual(tuple(rc.cache['you']), (d2,))
        # Test precedence; cache is the only keyword with higher precedence than rules
        c = rc.cache
        rc = RuleChecker(cache=c, rules=[d1, d2, d3])
        self.assertIs(rc.cache, c)

    def test_init_queryset(self):
        rc = RuleChecker(queryset=NotImplemented)
        self.assertIs(rc.cache.source.source, NotImplemented)
        self.assertTrue(isinstance(rc.cache, TopicalRuleCache))
        self.assertTrue(isinstance(rc.cache.source, RuleCache))
        rc = RuleChecker(cls=DifferentRuleCache, queryset=3)
        self.assertEqual(rc.cache.source.source, 3)
        self.assertFalse(isinstance(rc.cache, TopicalRuleCache))
        self.assertTrue(isinstance(rc.cache.source, RuleCache))
        # Test precendence; these keywords have precedence over queryset
        for k in ('cache', 'rules'):
            rc = RuleChecker(queryset=NotImplemented, **{k: RuleCache.default})
            self.assertFalse(isinstance(rc.cache.source, RuleCache))

    def test_init_source(self):
        rc = RuleChecker(source=NotImplemented)
        self.assertIs(rc.cache.source, NotImplemented)
        self.assertTrue(isinstance(rc.cache, TopicalRuleCache))
        rc = RuleChecker(cls=DifferentRuleCache, source=2)
        self.assertEqual(rc.cache.source, 2)
        self.assertFalse(isinstance(rc.cache, TopicalRuleCache))
        # Test precendence; these keywords have precedence over queryset
        for k in ('cache', 'rules', 'queryset'):
            rc = RuleChecker(source=NotImplemented, **{k: RuleCache.default})
            self.assertIsNot(rc.cache.source, NotImplemented)


class TestSignalChecker(TestCase):
    def setUp(self):
        from unittest import SkipTest
        raise SkipTest

    def test_init(self):
        self.assertRaises(ValueError, RuleChecker, None)
        rc = RuleChecker(self.user)
        self.assertEqual(len(rc.rules), 4)
        self.assertEqual(rc.models, frozenset((Individual, Population)))
        self.assertIs(rc.user, self.user)
        self.assertEqual(rc.objects, {})
        self.assertEqual(rc.errors, [])
        self.assertEqual(rc.warnings, [])
        self.assertEqual(rc.occurrences, [])

    def test_init_models(self):
        rc = RuleChecker(self.user, Individual)
        self.assertEqual(len(rc.rules), 3)

    def test_init_customer(self):
        rc = RuleChecker(self.user, customer=2)
        print([r.product_id for r in rc.rules])
        self.assertEqual(len(rc.rules), 3)
        self.user.is_superuser = True
        rc = RuleChecker(self.user)
        self.assertEqual(len(rc.rules), 3)

    def test_init_options(self):
        rc = RuleChecker(self.user)
        self.assertTrue(rc.save_occurrences)
        self.assertFalse(rc.need_pks)
        rc = RuleChecker(self.user, save_occurrences=False, need_pks=True)
        self.assertFalse(rc.save_occurrences)
        self.assertTrue(rc.need_pks)

    def test_init_rules(self):
        rc = RuleChecker(self.user, rules=Rule.objects.filter(pk=self.rule4.pk))
        self.assertEqual(rc.models, frozenset((Population,)))
        self.assertEqual(len(rc.rules), 1)

    def test_init_filters(self):
        rc = RuleChecker(self.user, when__in=('edit', 'exists'))
        self.assertEqual(len(rc.rules), 3)
        rc = RuleChecker(self.user, when='edit', type='warn')
        self.assertEqual(len(rc.rules), 1)

    def test_add_save_pk(self):
        with RuleChecker(self.user, Individual, need_pks=True) as rc:
            i = self.i.make(first_name='')
            self.assertEqual(len(rc.objects), 0)
            self.assertEqual(len(rc.occurrences), 1)
            self.assertEqual(len(rc.errors), 1)
            self.assertEqual(Occurrence.objects.count(), 1)
            self.assertIsNot(rc.occurrences[0].pk, None)
        self.assertEqual(Occurrence.objects.count(), 1)

    def test_add_save(self):
        with RuleChecker(self.user, Individual) as rc:
            i = self.i.make(first_name='')
            self.assertEqual(len(rc.objects), 0)
            self.assertEqual(len(rc.occurrences), 1)
            self.assertEqual(len(rc.errors), 1)
            self.assertEqual(Occurrence.objects.count(), 0)
            self.assertIs(rc.occurrences[0].pk, None)
        self.assertEqual(Occurrence.objects.count(), 1)
        self.assertIs(rc.occurrences[0].pk, None)

    def test_add_nosave(self):
        with RuleChecker(self.user, Individual, save_occurrences=False) as rc:
            i = self.i.make(first_name='')
            self.assertEqual(len(rc.objects), 0)
        self.assertEqual(len(rc.occurrences), 1)
        self.assertEqual(len(rc.errors), 1)
        self.assertEqual(Occurrence.objects.count(), 0)
        self.assertIs(rc.occurrences[0].pk, None)

    def test_edit_manual(self):
        i = self.i.make()
        with RuleChecker(self.user, Individual) as rc:
            self.assertEqual(len(rc.objects), 0)
            rc.track(i)
            self.assertEqual(len(rc.objects), 1)
            self.assertIn((Individual, i.pk), rc.objects)
            i.first_name = 'Glen'
            self.assertEqual(len(rc.occurrences), 0)
            i.save()
            self.assertEqual(len(rc.occurrences), 1)
            self.assertEqual(len(rc.errors), 0)
            self.assertEqual(len(rc.warnings), 1)
            self.assertEqual(Occurrence.objects.count(), 0)
        self.assertEqual(Occurrence.objects.count(), 1)

    def test_edit_automatic(self):
        self.i.make()
        with RuleChecker(self.user, Individual) as rc:
            i = Individual.objects.get()
            self.assertEqual(len(rc.objects), 1)
            self.assertIn((Individual, i.pk), rc.objects)
            i.first_name = 'Glen'
            self.assertEqual(len(rc.occurrences), 0)
            i.save()
            self.assertEqual(len(rc.occurrences), 1)
            self.assertEqual(len(rc.errors), 0)
            self.assertEqual(len(rc.warnings), 1)
            self.assertEqual(Occurrence.objects.count(), 0)
        self.assertEqual(Occurrence.objects.count(), 1)
