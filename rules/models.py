from django.db import models
from django.db.models.query import QuerySet
from django.core.exceptions import ValidationError
from django.core.urlresolvers import reverse

from madlibs.models.fields import JSONTextField
from .conf import settings
from .core import OR, ConditionNode


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


class BaseRule(models.Model):
    """Represents a business rule."""
    key = models.CharField(max_length=100, help_text='The key determines when this rule is '
                           'checked, e.g. when a row in the database is inserted or changed.')
    trigger = models.CharField(max_length=100, help_text='The name of the action triggered '
                               'when this rule is matched.')
    if settings.RULES_OWNER_MODEL:
        owner = models.ForeignKey(settings.RULES_OWNER_MODEL, blank=True, null=True,
                                  related_name='+')
    description = models.CharField(max_length=50, help_text='A short description of '
                                   'the purpose of the rule.')
    message = models.CharField(max_length=255, blank=True,
                               help_text='A message explaining why the rule was matched, '
                               'or what a match means, and how to resolve it. May be left '
                               'blank if description contains sufficient information.')
    result = JSONTextField(blank=True, help_text='A helper value which will be '
                           'passed to the trigger when the rule is matched.')
    tree = models.TextField(help_text='The string representation of the condition tree.')

    objects = RuleManager()

    def __str__(self):
        return self.description

    @property
    def is_system(self):
        return not getattr(self, 'owner_id', None)

    def _build_tree(self, conditions):
        if isinstance(conditions, ConditionNode):
            self._tree = conditions
        elif not conditions:
            # Make it so the rule is never matched.
            self._tree = ConditionNode(connector=OR)
        else:
            # TODO parse
            self._tree = root

    @property
    def conditions(self):
        if '_tree' not in self.__dict__:
            self._build_tree(self.tree)
        return self._tree

    @conditions.setter
    def conditions(self, value):
        self._build_tree(value)
        #TODO self.tree = self._tree.to_str()

    def match(self, *objects, **extra):
        """Matches the given arguments against this rule."""
        return self.conditions._evaluate({'objects': objects, 'extra': extra})

    def _match(self, info):
        return self.conditions._evaluate(info)

    class Meta:
        abstract = True


if settings.RULES_CONCRETE_MODELS:
    class Rule(BaseRule):
        def get_absolute_url(self):
            """For now we'll just use the admin, but eventually we'll want a view customers can use."""
            return reverse('admin:rule_reactor_rule_change', args=[self.pk])
