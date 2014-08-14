from django.db import models
from django.db.models.query import QuerySet
from django.core.exceptions import ValidationError
from django.core.urlresolvers import reverse

from madlibs.models.fields import JSONTextField
from .cache import RuleCache, TopicalRuleCache
from .conf import settings
from .core import Rule as CoreRule


class RuleQueryMixin(object):
    """Adds query methods to both :class:`RuleSet` and :class:`RuleManager`."""

    if settings.RULES_OWNER_MODEL:
        def for_owner(self, owner):
            """Returns both system rules and rules belonging to the given owner."""
            return self.filter(models.Q(owner=owner) | models.Q(owner__isnull=True))
 
        def system(self):
            """Returns only system rules (rules without an associated owner)."""
            return self.filter(customer__isnull=True)


class RuleSet(RuleQueryMixin, QuerySet):
    """
    Queryset for rules with a few special filters (from :class:`RuleQueryMixin` and a bulk
    :meth:`matches` method.
    """

    def matches(self, *objects, **extra):
        """Checks the given objects against all the rules in the QuerySet, returning matches."""
        info = {'objects': objects, 'extra': extra}
        return [r for r in self if r._match(info)]


class RuleManager(RuleQueryMixin, models.Manager):
    """Manager with a couple of helpful methods for working with :class:`Rule`s."""

    def get_query_set(self):
        """Default ``QuerySet`` type for rules is :class:`RuleSet`."""
        return RuleSet(self.model, using=self._db)


class BaseRule(CoreRule, models.Model):
    """Represents a business rule."""
    trigger = models.CharField(max_length=100, help_text='The trigger determines when '
                               'this rule is checked, e.g. when a row in the database '
                               'is inserted or changed.')
    continuation = models.CharField(max_length=100, help_text='The name of the action '
                                    'called when this rule is matched.')
    if settings.RULES_OWNER_MODEL:
        owner = models.ForeignKey(settings.RULES_OWNER_MODEL, blank=True, null=True,
                                  related_name='+')
    description = models.CharField(max_length=50, help_text='A short description of '
                                   'the purpose of the rule.')
    message = models.CharField(max_length=255, blank=True,
                               help_text='A message explaining why the rule was matched, '
                               'or what a match means, and how to resolve it. May be left '
                               'blank if description contains sufficient information.')
    value = JSONTextField(blank=True, help_text='A helper value which will be '
                          'passed to the continuation when the rule is matched.')
    tree = models.TextField(help_text='The string representation of the condition tree.')
    weight = models.IntegerField(default=0, blank=True)

    objects = RuleManager()

    def __init__(self, *args, **kwargs):
        models.Model.__init__(self, *args, **kwargs)

    def __str__(self):
        return self.description

    @property
    def is_system(self):
        return not getattr(self, 'owner_id', None)

    @property
    def conditions(self):
        if '_tree' not in self.__dict__:
            self._tree = self._build_tree(self.tree)
        return self._tree

    @conditions.setter
    def conditions(self, value):
        self._tree = self._build_tree(value)
        #TODO self.tree = self._tree.to_str()

    class Meta:
        abstract = True


def expand_model_key(key):
    '''key types
    * create.<app_label>.<model>:<signal>
    * update.<ditto>
    * delete.<ditto>
    '''
    sig = ''
    if ':' in key:
        key, sig = key.split(':')
    parts = key.split('.')
    if parts[0] in ('create', 'update', 'delete') and len(parts) == 3:
        if sig in ('pre_save', 'pre_delete'):
            sig = ':' + sig
        elif sig not in ('post_delete', 'post_save', ''):
            raise ValueError('Unsupported signal: "{}"'.format(sig))
        is_delete = parts[0] == 'delete'
        if (is_delete and 'save' in sig) or (not is_delete and 'delete' in sig):
            msg = 'Signal does not match event: "{}" vs. "{}"'
            raise ValueError(msg.format(parts[0], sig))
        elif 'post' in sig:
            sig = ''
        keys = ['#', '#.{1}.{2}', '#.{1}.#', '{0}.#', '{0}.{1}.#', '{0}.{1}.{2}']
        return tuple(k.format(*parts) + sig for k in keys)
    return NotImplemented


if settings.RULES_CONCRETE_MODELS:
    class Rule(BaseRule):
        def get_absolute_url(self):
            """For now we'll just use the admin, but eventually we'll want a view customers can use."""
            return reverse('admin:rule_reactor_rule_change', args=[self.pk])

    RuleCache.default = RuleCache(Rule.objects)
    TopicalRuleCache.default = TopicalRuleCache(RuleCache.default, [expand_model_key])
