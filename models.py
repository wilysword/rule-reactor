from copy import deepcopy

from django.db import models
from django.db.models.query import QuerySet
from django.db.models.sql.where import Constraint, AND
from django.contrib.contenttypes.models import ContentType
from django.contrib.contenttypes.generic import GenericForeignKey
from django.core.validators import validate_email, ValidationError
from django.core.serializers.python import Serializer, Deserializer
from django.core.urlresolvers import reverse
from django.utils import timezone
from madlibs.models.fields import DictField, JSONTextField

from falcon.core.models import Customer, Product, User
from .matchers import MATCHERS


def validate_email_list(value):
    errors = []
    for email in value:
        try:
            validate_email(email)
        except ValidationError:
            errors.append(email)
    if errors:
        msg = 'The following are not valid emails: {}'.format(', '.join(errors))
        raise ValidationError(msg, code=validate_email.code)


class RuleQueryMixin(object):
    """Adds query methods to both :class:`RuleSet` and :class:`RuleManager`."""

    def for_customer(self, customer):
        """Returns both system rules and rules belonging to the given customer."""
        return self.filter(models.Q(customer=customer) | models.Q(customer__isnull=True))

    def system(self):
        """Returns only system rules (rules without an associated customer)."""
        return self.filter(customer__isnull=True)

    def for_models(self, *models):
        """Returns only rules associated with the given models."""
        cts = [ct for _, ct in ContentType.objects.get_for_models(*models).items()]
        return self.filter(table__in=cts)


class RuleSet(RuleQueryMixin, QuerySet):
    """
    Queryset for rules with a few special filters (from :class:`RuleQueryMixin` and a bulk
    :meth:`matches` method.
    """

    def matches(self, old_obj, new_obj, product_id=None):
        """Checks the given objects against all the rules in the QuerySet, returning matches."""
        return [r for r in self if r.match(old_obj, new_obj, product_id)]


class RuleManager(RuleQueryMixin, models.Manager):
    """Manager with a couple of helpful methods for working with :class:`Rule`s."""

    def get_query_set(self):
        """Default ``QuerySet`` type for rules is :class:`RuleSet`."""
        return RuleSet(self.model, using=self._db).select_related('table')

    def create_for_model(self, model, **kwargs):
        """Shortcut for creating a rule without having to look up the correct ContentType."""
        ct = ContentType.objects.get_for_model(model)
        kwargs['table'] = ct
        return self.create(**kwargs)


class Rule(models.Model):
    """
    Represents a business rule related to other objects in the database.

    These rules can technically be checked any time, but are grouped into 'expected' check
    times: 'add', 'edit', and 'delete' being obvious, with 'exists' and 'not exists' normally
    being checked on both adds and edits.

    Since the rules don't define what happens when they are matched, other code can freely
    define what it means to match a rule. There are types, however, which correspond to
    *expected* behavior (though that behavior is not enforced by the Rule Reactor): 'error'
    and 'warning'.

    'error' rules are expected to be triggered when a model is modified in such a way that it
    does not violate database constraints, but nonetheless leaves an object in an 'invalid' state.

    'warning' rules correspond to object states which, while not necessarily invalid, are at
    least unexpected, and should be reviewed by a human.
    """
    TIMES = (
        ('add', 'add'),
        ('edit', 'edit'),
        ('delete', 'delete'),
        ('exists', 'exists'),
        ('not exists', 'does not exist'),
    )
    TYPES = (
        ('error', 'error'),
        ('warn', 'warning'),
        ('notify', 'notification'),
    )
    table = models.ForeignKey(ContentType, related_name='trigger_rules', help_text=
                              'The model whose instances can match this rule.')
    customer = models.ForeignKey(Customer, blank=True, null=True, related_name='trigger_rules',
                                 help_text='The customer to whom this rule belongs. If null, '
                                 'this is a rule which applies to all customers.')
    product = models.ForeignKey(Product, blank=True, null=True, related_name='trigger_rules',
                                help_text='If the rule is associated with a product, it will '
                                'only match an object when the product_id is provided at '
                                'match time. This is useful for product-specific required '
                                'fields, such as SSN for SSA DMF.')
    message = models.CharField(max_length=255, help_text='A message explaining why the rule '
                               'was matched, or what a match means.')
    emails = JSONTextField(blank=True, default=[], validators=[validate_email_list],
                           help_text='A list of emails of people who should be notified when '
                           'this rule is matched.')
    type = models.CharField(max_length=10, choices=TYPES)
    when = models.CharField(max_length=10, choices=TIMES, help_text='When the rule should be checked.')
    conditions = DictField(blank=True, default={}, help_text='Additional constraints on how '
                           'a rule is matched. Valid keys depend on when the rule is checked; '
                           'see function docstrings in matchers.py for specifics.')

    objects = RuleManager()

    def __str__(self):
        return '{0.type}: {0.when}'.format(self)

    @property
    def is_system(self):
        return not self.customer_id

    def _compare_when(self, old_obj, new_obj):
        """
        Ensures the given objects match this rule's 'when', e.g. if only new_obj is given it's
        an add, if only old_obj is given it's a delete, etc.
        """
        if self.when in ('exists', 'not exists'):
            return bool(new_obj)
        if old_obj and new_obj:
            return self.when == 'edit'
        elif new_obj:
            return self.when == 'add'
        elif old_obj:
            return self.when == 'delete'

    def match(self, old_obj, new_obj, product_id=None):
        """
        Matches the given arguments against this rule.

        Returns False if:
            * product_id is given and does not match the rule's product (or the rule has none).
            * :meth:`_compare_when` returns False
            * Either of the given objects are not of the correct type.
            * The matcher from matchers.py returns False.
        """
        if product_id and product_id != self.product_id:
            return False
        if not self._compare_when(old_obj, new_obj):
            return False
        model = self.table.model_class()
        if (old_obj and not isinstance(old_obj, model)) or (new_obj and not isinstance(new_obj, model)):
            return False
        return MATCHERS[self.when](self, old_obj, new_obj)

    def get_absolute_url(self):
        """For now we'll just use the admin, but eventually we'll want a view customers can use."""
        return reverse('admin:rule_reactor_rule_change', args=[self.pk])


class OccQueryMixin(object):
    def unresolved(self):
        """Returns only occurrences with null resolution_date."""
        return self.filter(resolution_date__isnull=True)

    def unresolved_for_object(self, obj):
        """Returns all unresolved occurrences associated with the given object."""
        table = ContentType.objects.get_for_model(type(obj))
        return self.unresolved().filter(rule__table=table, object_id=obj.pk)

    def for_customer(self, customer):
        """Returns both system rules and rules belonging to the given customer."""
        return self.filter(models.Q(rule__customer=customer) | models.Q(rule__customer__isnull=True))

    def system(self):
        """Returns only system rules (rules without an associated customer)."""
        return self.filter(rule__customer__isnull=True)


class OccurrenceSet(OccQueryMixin, QuerySet):
    def exclude_from(self, obj_queryset):
        """
        Excludes from the given queryset any objects with occurrences in this queryset.

        Like restrict, uses a subquery. To guarantee the subquery, passes the Query as
        the value, rather than the QuerySet (which can sometimes be evaluated and passed
        as a list, rather than executed as a subquery).
        """
        ct = ContentType.objects.get_for_model(obj_queryset.model)
        queryset = self.filter(rule__table=ct).values_list('object_id')
        return obj_queryset.exclude(pk__in=queryset.query)

    def restrict(self, obj_queryset):
        """
        Restricts the given queryset to only objects with occurrences in this queryset.

        Although a JOIN is slightly more efficient than a subquery in most instances, it
        requires much hacking into the internals of the Django ORM (because the models aren't
        explicitly related), so we'll use the subquery here.
        """
        ct = ContentType.objects.get_for_model(obj_queryset.model)
        queryset = self.filter(rule__table=ct).values_list('object_id')
        return obj_queryset.filter(pk__in=queryset.query)

    def resolve(self, user, message):
        return self.update(resolved_by=user, resolution_message=message, resolution_date=timezone.now())


class OccurrenceManager(OccQueryMixin, models.Manager):
    def get_query_set(self):
        """Default ``QuerySet`` type for occurrences is :class:`OccurrenceSet`."""
        return OccurrenceSet(self.model, using=self._db)

    def create_for_rules(self, user, obj, rules=None, old_obj=None, product_id=None):
        """
        Bulk create occurrences for any matches amongst the given rules.

        If no rules are given, a queryset is created for all system rules for the type
        of the given object (and the product, if given).
        """
        if rules is None:
            rules = Rule.objects.system().for_models(type(obj))
            if product_id:
                rules = rules.filter(product_id=product_id)
            else:
                rules = rules.filter(product__isnull=True)
        matches = rules.matches(old_obj, obj, product_id)

        # Serialize it just once
        old_obj = Occurrence(old_object=old_obj).old_obj
        self.bulk_create(
            [Occurrence(object_id=obj.pk, rule=rule, user_id=user.pk, old_obj=old_obj) for rule in matches]
        )

    def try_resolve(self, user, obj):
        """
        Checks any unresolved occurrences associated with the given object, and whether the
        rules are still matches.

        This method can be used to automatically resolve certain rules when an edit is made
        to an object; for example, if a rule that requires a certain field was matched on an
        add, the user can edit the object and add the field: since the rule then no longer
        matches, the occurrence can be resolved automatically by passing the new version of
        the object. Of course, edit rules should still be checked separately.

        .. note::
            This was mostly designed to work for errors and warnings, so if other meanings
            are given to occurrences in the future, care should be taken that they are not
            resolved when they shouldn't be.
        """
        unresolved = self.unresolved_for_object(obj).select_related('rule', 'rule__table')
        still = []
        checked = []
        for occ in unresolved:
            occ.object = obj
            if not occ.try_resolve(user, save=False):
                still.append(occ.pk)
            checked.append(occ.rule.pk)
        resolved = unresolved.exclude(pk__in=still)
        resolved.update(resolution_date=timezone.now(), resolved_by=user.pk, resolution_message='automatic')
        return checked


# TODO is there a better name for this model?
class Occurrence(models.Model):
    """Represents the occurrence of a rule match."""
    rule = models.ForeignKey(Rule)
    object_id = models.IntegerField(help_text='The PK of the object that was matched by the '
                                    'rule. Should be 0 for "delete" rules.')
    user = models.ForeignKey(User, help_text='The user whose action with the object caused '
                             'the rule to be matched.')
    old_obj = JSONTextField(blank=True, default='', help_text='The serialized version of the '
                            "'old_obj' argument in the rule's match, if one was given.")
    creation_date = models.DateTimeField(auto_now_add=True)
    resolution_date = models.DateTimeField(blank=True, null=True)
    resolved_by = models.ForeignKey(User, blank=True, null=True, related_name='occurrences_resolved')
    resolution_message = models.CharField(max_length=100, blank=True, default='',
                                          help_text='A message explaining why/how the occurrence '
                                          'was resolved, especially if being resolved manually.')
    # Link to reversion tables? At least for edits, a link to the old data so the caller doesn't
    # have to provide it...

    @property
    def object(self):
        """
        The object which was matched to the rule.

        For deletes this will return the same as ``old_object``; otherwise it returns the
        object's current version, not as it was when the rule was matched.
        """
        if not self.object_id:
            return self.old_object
        if '_cached_object' not in self.__dict__:
            model = self.rule.table.model_class()
            self._cached_object = model.objects.get(pk=self.object_id)
        return self._cached_object

    @object.setter
    def object(self, obj):
        if not obj:
            self.object_id = 0
        elif type(obj) != self.rule.table.model_class():
            raise ValueError('Attempted to assign incorrect type to occurrence')
        else:
            self._cached_object = obj
            self.object_id = obj.pk

    @property
    def old_object(self):
        """For edits and deletes, the old version of the object used to match the rule."""
        if '_cached_old' not in self.__dict__:
            self._cached_old = Deserializer(self.old_obj)[0] if self.old_obj else None
        return self._cached_old

    @old_object.setter
    def old_object(self, old_obj):
        self._cached_old = old_obj
        self.old_obj = Serializer().serialize((old_obj,)) if old_obj else ''

    objects = OccurrenceManager()

    @property
    def is_resolved(self):
        return bool(self.resolution_date)

    def try_resolve(self, user, save=True):
        """
        Checks the rule using the cached old version of the object (if it exists) and the
        current version of the object; if it no longer matches, :meth:`resolve` is called.
        """
        if self.rule.when == 'delete':
            match = self.rule.match(self.object, None)
        else:
            match = self.rule.match(self.old_object, self.object)
        # If this rule, which was previously a match, is now not a match, the occurrence has been resolved
        if not match:
            self.resolve(user, 'automatic', save=save)
        return not match

    def resolve(self, user, message, save=True):
        """Sets the resolution_date, resolved_by, and resolution_method fields."""
        self.resolution_date = timezone.now()
        self.resolved_by_id = user.pk if user else None
        self.resolution_message = message
        if save:
            self.save()
