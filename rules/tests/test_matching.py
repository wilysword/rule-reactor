import copy

from django.contrib.contenttypes.models import ContentType
from django.test import TestCase
from django.utils.timezone import now
from model_mommy import mommy

from rule_reactor.matchers import *
# To make things simpler we'll test against rule instances.
from rule_reactor.models import Rule


class Base(TestCase):
    def _combine(self, into, kwargs):
        for key, val in kwargs.items():
            if isinstance(val, dict) and key in into:
                self._combine(into[key], val)
            else:
                into[key] = val

    def _collect_kwargs(self, key, kwargs):
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

    def get_rule(self, **kwargs):
        kwargs = self._collect_kwargs('rkwargs', kwargs)
        if 'table' not in kwargs:
            kwargs['table'] = ContentType.objects.get_for_model(Rule)
        if 'when' not in kwargs and hasattr(self, 'when'):
            kwargs['when'] = self.when
        return mommy.make(Rule, **kwargs)


class TestAddMatch(Base):
    when = 'add'

    def _match(self, *args):
        return add_match(args[0], args[2])

    def test_simple(self):
        r = self.get_rule()
        self.assertTrue(self._match(r, None, r))
        self.assertFalse(self._match(r, None, None))
        # Second field is ignored
        self.assertFalse(self._match(r, r, None))
        # However, the rule uses all three fields to validate when.
        if not isinstance(self, RuleMatchMixin):
            self.assertTrue(self._match(r, r, r))
        if not isinstance(self, RuleSetMatchMixin):
            self.assertRaises(AttributeError, self._match, None, None, r)

    def test_fields(self):
        r = self.get_rule(conditions={'fields': ['message', 'type']})
        self.assertTrue(self._match(r, None, r))
        r.message = ''
        self.assertFalse(self._match(r, None, r))
        r.message = 'hello'
        self.assertTrue(self._match(r, None, r))
        r.type = ''
        self.assertFalse(self._match(r, None, r))

    def test_values(self):
        r = self.get_rule(conditions={'new_values': {'message': ['hello', 'goodbye'],
                                                     'type': ['error', '']}},
                          type='error', message='hello')
        self.assertTrue(self._match(r, None, r))
        r.message = ''
        self.assertFalse(self._match(r, None, r))
        r.message = 'goodbye'
        self.assertTrue(self._match(r, None, r))
        r.type = ''
        self.assertTrue(self._match(r, None, r))
        r.type = 'warn'
        self.assertFalse(self._match(r, None, r))

    def test_fields_and_values(self):
        r = self.get_rule(conditions={'new_values': {'message': ['hello', 'goodbye'],
                                                     'type': ['error', '']},
                                      'fields': ['customer_id', 'type']},
                          type='error', message='hello', customer__inactive_date=now())
        self.assertTrue(self._match(r, None, r))
        r.message = ''
        self.assertFalse(self._match(r, None, r))
        r.message = 'goodbye'
        self.assertTrue(self._match(r, None, r))
        # From fields this would be invalid, but the values dict overrides that.
        r.type = ''
        self.assertTrue(self._match(r, None, r))
        r.type = 'warn'
        self.assertFalse(self._match(r, None, r))
        r.type = 'error'
        self.assertTrue(self._match(r, None, r))
        r.customer = None
        self.assertFalse(self._match(r, None, r))


class TestExistsMatch(TestAddMatch):
    when = 'exists'

    def _match(self, *args):
        return exists_match(args[0], args[2])

    def test_model(self):
        r = self.get_rule(conditions={'model': 'rule_reactor.rule'})
        self.assertTrue(self._match(r, None, r))
        # Second field is ignored
        self.assertFalse(self._match(r, r, None))
        self.assertTrue(self._match(r, r, r))
        if not isinstance(self, RuleSetMatchMixin):
            self.assertRaises(AttributeError, self._match, None, None, r)

        r.delete()
        self.assertFalse(self._match(r, None, r))

    def test_model_filters(self):
        r = self.get_rule(type='error', conditions={'model': 'rule_reactor.rule', 'filters': {'type': 'warn'}})
        self.assertFalse(self._match(r, None, r))
        r.type = 'warn'
        r.save()
        self.assertTrue(self._match(r, None, r))

    def test_model_filters_none(self):
        ct = ContentType.objects.get_for_model(ContentType)
        r = self.get_rule(type='error', table=ct,
                          conditions={'model': 'rule_reactor.rule', 'filters': {'table': None}})
        rct = ContentType.objects.get_for_model(Rule)
        self.assertFalse(self._match(r, None, rct))
        self.assertTrue(self._match(r, None, ct))


class TestDeleteMatch(Base):
    when = 'delete'

    def _match(self, *args):
        return delete_match(args[0], args[1])

    def test_simple(self):
        r = self.get_rule()
        self.assertTrue(self._match(r, r, None))
        self.assertFalse(self._match(r, None, None))
        # Second field is ignored
        self.assertFalse(self._match(r, None, r))
        # However, the rule uses all three fields to validate when.
        if not isinstance(self, RuleMatchMixin):
            self.assertTrue(self._match(r, r, r))
        if not isinstance(self, RuleSetMatchMixin):
            self.assertRaises(AttributeError, self._match, None, r, None)

    def test_fields(self):
        r = self.get_rule(conditions={'fields': ['message', 'type']})
        self.assertTrue(self._match(r, r, None))
        r.message = ''
        self.assertFalse(self._match(r, r, None))
        r.message = 'hello'
        self.assertTrue(self._match(r, r, None))
        r.type = ''
        self.assertFalse(self._match(r, r, None))

    def test_values(self):
        r = self.get_rule(conditions={'old_values': {'message': ['hello', 'goodbye'],
                                                     'type': ['error', '']}},
                          type='error', message='hello')
        self.assertTrue(self._match(r, r, None))
        r.message = ''
        self.assertFalse(self._match(r, r, None))
        r.message = 'goodbye'
        self.assertTrue(self._match(r, r, None))
        r.type = ''
        self.assertTrue(self._match(r, r, None))
        r.type = 'warn'
        self.assertFalse(self._match(r, r, None))

    def test_fields_and_values(self):
        r = self.get_rule(conditions={'old_values': {'message': ['hello', 'goodbye'],
                                                     'type': ['error', '']},
                                      'fields': ['customer_id', 'type']},
                          type='error', message='hello', customer__inactive_date=now())
        self.assertTrue(self._match(r, r, None))
        r.message = ''
        self.assertFalse(self._match(r, r, None))
        r.message = 'goodbye'
        self.assertTrue(self._match(r, r, None))
        # From fields this would be invalid, but the values dict overrides that.
        r.type = ''
        self.assertTrue(self._match(r, r, None))
        r.type = 'warn'
        self.assertFalse(self._match(r, r, None))
        r.type = 'error'
        self.assertTrue(self._match(r, r, None))
        r.customer = None
        self.assertFalse(self._match(r, r, None))


class TestEditMatch(Base):
    when = 'edit'

    def _match(self, *args):
        return edit_match(*args)

    def test_simple(self):
        r = self.get_rule()
        self.assertFalse(self._match(r, None, None))
        self.assertFalse(self._match(r, r, None))
        self.assertFalse(self._match(r, None, r))
        r1 = copy.copy(r)
        self.assertFalse(self._match(r, r, r1))
        r1.customer_id = 5
        self.assertTrue(self._match(r, r, r1))
        # unless checking for specific values, order isn't important
        self.assertTrue(self._match(r, r1, r))
        if not isinstance(self, RuleSetMatchMixin):
            self.assertRaises(AttributeError, self._match, None, r, r1)

    def test_new_values(self):
        r = self.get_rule(conditions={'new_values': {'message': ['hello', 'goodbye'],
                                                     'type': ['error', '']}},
                          type='error', message='hello')
        r1 = copy.copy(r)
        # although the values match, there still has to be at least one field difference
        self.assertFalse(self._match(r, r, r1))
        r.type = 'warn'
        r.message = 'sdghlshddg'
        # not checking old values
        self.assertTrue(self._match(r, r, r1))
        # now order is important
        self.assertFalse(self._match(r, r1, r))
        r1.type = 'notify'
        self.assertFalse(self._match(r, r, r1))
        r1.type = ''
        self.assertTrue(self._match(r, r, r1))
        r1.message = 'hskdgh'
        self.assertFalse(self._match(r, r, r1))
        r1.message = 'goodbye'
        self.assertTrue(self._match(r, r, r1))

    def test_old_values(self):
        r = self.get_rule(conditions={'old_values': {'message': ['hello', 'goodbye'],
                                                     'type': ['error', '']}},
                          type='error', message='hello')
        r1 = copy.copy(r)
        # although the values match, there still has to be at least one field difference
        self.assertFalse(self._match(r, r1, r))
        r.type = 'warn'
        r.message = 'sdghlshddg'
        # not checking old values
        self.assertTrue(self._match(r, r1, r))
        # now order is important
        self.assertFalse(self._match(r, r, r1))
        r1.type = 'notify'
        self.assertFalse(self._match(r, r1, r))
        r1.type = ''
        self.assertTrue(self._match(r, r1, r))
        r1.message = 'hskdgh'
        self.assertFalse(self._match(r, r1, r))
        r1.message = 'goodbye'
        self.assertTrue(self._match(r, r1, r))

    def test_fields(self):
        r = self.get_rule(type='error', conditions={'fields': ['message', 'type']})
        r1 = copy.copy(r)
        self.assertFalse(self._match(r, r, r1))
        r1.customer_id = 5
        # if fields are present, only those fields are checked
        self.assertFalse(self._match(r, r, r1))
        r1.message = 'skdghlsdhg'
        self.assertFalse(self._match(r, r, r1))
        r1.message = r.message
        r1.type = 'warn'
        self.assertFalse(self._match(r, r, r1))
        r1.message = 'sdhgksdhkfgsdg'
        self.assertTrue(self._match(r, r1, r))
        # unless checking for specific values, order isn't important
        self.assertTrue(self._match(r, r1, r))

    def test_all(self):
        conditions = {
            'new_vals': {'message': ['goodbye', 'bye', 'one'], 'type': ['error']},
            'old_vals': {'message': ['hello', 'hi', 'one'], 'customer_id': [None]},
            'fields': ['type', 'customer_id']
        }
        r = self.get_rule(type='error', message='hello', conditions=conditions)
        r1 = copy.copy(r)
        self.assertFalse(self._match(r, r, r1))
        r1.message = 'bye'
        self.assertFalse(self._match(r, r, r1))
        r.type = 'warn'
        self.assertFalse(self._match(r, r, r1))
        r1.customer_id = 5
        self.assertTrue(self._match(r, r, r1))
        # message doesn't have to change as long as the value appears in both lists
        r1.message = 'one'
        r.message = 'one'
        self.assertTrue(self._match(r, r, r1))


# These ensure that compatible functionality is the same between all ways of calling match.
class MatchersDictMixin(object):
    def _match(self, *args):
        return MATCHERS[self.when](*args)


class RuleMatchMixin(object):
    def _match(self, rule, *args):
        return rule.match(*args)


class RuleSetMatchMixin(RuleMatchMixin):
    def _match(self, rule, *args):
        return len(Rule.objects.all().matches(*args)) == 1


for symbol, item in locals().items():
    if isinstance(item, type) and issubclass(item, Base) and item != Base:
        exec('Matchers{0} = type("Matchers{0}", (MatchersDictMixin, {0}), {{}})'.format(symbol))
        exec('Rule{0} = type("Rule{0}", (RuleMatchMixin, {0}), {{}})'.format(symbol))
        exec('RuleSet{0} = type("RuleSet{0}", (RuleSetMatchMixin, {0}), {{}})'.format(symbol))
