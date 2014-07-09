from datetime import date, datetime

from dateutil.parser import parse as parse_date
from django.db import models
from django.db.models.query import QuerySet
from django.contrib.contenttypes.models import ContentType
from django.core.exceptions import ValidationError
from django.core.urlresolvers import reverse
from django.utils import timezone
import six

from madlibs.models.fields import JSONTextField
from .conf import settings
from .core import AND, OR, ConditionNode, Condition as CoreCondition


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
        return [r for r in self if r._match(objects, extra)]

    # TODO need to be able to cache rules/conditions as a single unit


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
            ids = set(c.pk for c in conditions)
            pids = set(c.parent_id for c in conditions if c.parent_id)
            if pids - ids:
                raise ValueError('Missing parents: {}'.format(pids - ids))
            nodes = {pid: ConditionNode() for pid in pids}
            root = ConditionNode()
            for condition in conditions:
                parent = nodes.get(condition.parent_id, root)
                parent.add(condition, condition.connector)
                if condition.pk in nodes:
                    parent.add(nodes[condition.pk], condition.connector)
            self._tree = root

    @property
    def tree(self):
        if '_tree' not in self.__dict__:
            self._build_tree(self.conditions.all())
        return self._tree

    @tree.setter
    def tree(self, value):
        self._build_tree(value)

    def match(self, *objects, **extra):
        """Matches the given arguments against this rule."""
        return self.tree._evaluate(objects, extra)

    def _match(self, objects, extra):
        return self.tree._evaluate(objects, extra)

    class Meta:
        abstract = True


class ConditionManager(models.Manager):
    def get_query_set(self):
        """In most situations, we don't want to see internal conditions."""
        qs = super(ConditionManager, self).get_query_set()
        qs.query.add_q(~models.Q(left='int'))
        return qs

    def _all(self):
        """If we do need to see internal conditions, start here."""
        return super(ConditionManager, self).get_query_set()


class BaseCondition(CoreCondition, models.Model):
    COMPARISONS = (
        ('==', 'equals'),
        ('re', 'matches regular expression'),
        ('<', 'is less than'),
        ('<=', 'is less than or equal to'),
        ('in', 'is in'),
        ('bool', 'exists'),
    )
    KWARGS = CoreCondition.KWARGS + ('connector', 'pk')

    negated = models.BooleanField(default=False)
    operator = models.CharField(max_length=10, choices=COMPARISONS, default='exists')
    left = models.CharField(max_length=150)
    right = models.CharField(max_length=150, blank=True)
    value = JSONTextField(blank=True, default='')
    connector = models.CharField(max_length=3, choices=((AND, AND), (OR, OR)), default=AND)

    objects = ConditionManager()

    def __init__(self, *args, **kwargs):
        # Model and Condition init are not compatible, so we've got to work a bit
        # to get them to go together.
        if args:
            # args are pretty much only used by the ORM, so it's definitely a Model init.
            models.Model.__init__(self, *args, **kwargs)
        else:
            # Otherwise, we still need to init the Model, but we'll let the Condition
            # set attribute values in case they're using the special Condition syntax.
            models.Model.__init__(self)
            CoreCondition.__init__(self, **kwargs)
            for k in kwargs:
                if k in CoreCondition.KWARGS or k not in self.KWARGS:
                    continue
                setattr(self, k, kwargs[k])

    def clean(self):
        super(BaseCondition, self).clean()

    def _try_match_type(self, left, right):
        # Since value is stored as JSON, and dates/datetimes aren't automatically loaded
        # by json.loads, we may have to convert before we can compare
        if isinstance(right, six.string_types) and not isinstance(left, six.string_types):
            try:
                if isinstance(left, datetime):
                    right = parse_date(right)
                    # Assume local time
                    if timezone.is_aware(left) and timezone.is_naive(right):
                        right = timezone.make_aware(right, timezone.get_current_timezone())
                    elif timezone.is_naive(left) and timezone.is_aware(right):
                        right = timezone.make_naive(right, timezone.get_current_timezone())
                elif isinstance(left, date):
                    right = parse_date(right).date()
            except:
                pass
        return left, right

    def _evaluate(self, objects, extra):
        if self.left == 'int':
            # We don't want this to affect the final result, so we return True for AND
            # and False for OR; that way the result will be determined by other nodes.
            return self.connector == AND
        return super(BaseCondition, self)._evaluate(objects, extra)

    class Meta:
        abstract = True


if settings.RULES_CONCRETE_MODELS:
    class Rule(BaseRule):
        def get_absolute_url(self):
            """For now we'll just use the admin, but eventually we'll want a view customers can use."""
            return reverse('admin:rule_reactor_rule_change', args=[self.pk])
    # ssa_dmf(product_id) :- equal(product_id, 46)
    # bad_ssn(object, product_id) :- equal(object.ssn, ''), ssa_dmf(product_id)

    # VS

    # bad_ssn = Condition.C(o0__ssn__exists=False, extra__product_id=46)

    class Condition(BaseCondition):
        KWARGS = BaseCondition.KWARGS + ('id', 'rule', 'rule_id', 'parent', 'parent_id')

        rule = models.ForeignKey(Rule, related_name='conditions')
        parent = models.ForeignKey('self', blank=True, null=True, related_name='+')
