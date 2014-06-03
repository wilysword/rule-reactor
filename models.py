from copy import deepcopy

from django.db import models
from django.db.models.query import QuerySet
from django.db.models.sql.where import Constraint, AND
from django.contrib.contenttypes.models import ContentType
from django.contrib.contenttypes.generic import GenericForeignKey
from django.core.validators import validate_email, ValidationError
from django.core.serializers.python import Serializer, Deserializer
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
    def for_customer(self, customer):
        return self.filter(models.Q(customer=customer) | models.Q(customer__isnull=True))

    def system(self):
        return self.filter(customer__isnull=True)

    def for_models(self, *models):
        cts = [ct for _, ct in ContentType.objects.get_for_models(*models).items()]
        return self.filter(table__in=cts)


class RuleSet(RuleQueryMixin, QuerySet):
    def matches(self, old_obj, new_obj, product_id=None):
        return [r for r in self if r.match(old_obj, new_obj, product_id)]


class RuleManager(RuleQueryMixin, models.Manager):
    def get_query_set(self):
        return RuleSet(self.model, using=self._db).select_related('table')

    def create_for_model(self, model, **kwargs):
        ct = ContentType.objects.get_for_model(model)
        kwargs['table'] = ct
        return self.create(**kwargs)


class Rule(models.Model):
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
    table = models.ForeignKey(ContentType, related_name='trigger_rules')
    customer = models.ForeignKey(Customer, blank=True, null=True, related_name='trigger_rules')
    product = models.ForeignKey(Product, blank=True, null=True, related_name='trigger_rules')
    message = models.CharField(max_length=255)
    emails = JSONTextField(blank=True, default=[], validators=[validate_email_list])
    type = models.CharField(max_length=10, choices=TYPES)
    when = models.CharField(max_length=10, choices=TIMES)
    conditions = DictField(blank=True, default={})

    objects = RuleManager()

    @property
    def is_system(self):
        return not self.customer_id

    def _compare_when(self, old_obj, new_obj):
        if self.when in ('exists', 'not exists'):
            return bool(new_obj)
        if old_obj and new_obj:
            return self.when == 'edit'
        elif new_obj:
            return self.when == 'add'
        elif old_obj:
            return self.when == 'delete'

    def match(self, old_obj, new_obj, product_id=None):
        if product_id and product_id != self.product_id:
            return False
        if not self._compare_when(old_obj, new_obj):
            return False
        model = self.table.model_class()
        if (old_obj and not isinstance(old_obj, model)) or (new_obj and not isinstance(new_obj, model)):
            return False
        return MATCHERS[self.when](self, old_obj, new_obj)


class OccQueryMixin(object):
    def unresolved(self):
        return self.filter(resolution_date__isnull=True)

    def unresolved_for_object(self, obj):
        table = ContentType.objects.get_for_model(type(obj))
        return self.unresolved().filter(rule__table=table, object_id=obj.pk)


class OccurrenceSet(OccQueryMixin, QuerySet):
    def restrict(self, obj_queryset):
        model = obj_queryset.model
        ct = ContentType.objects.get_for_model(model)
        qs = obj_queryset._clone()
        alias = qs.query.get_initial_alias()
        occ_alias = self._join(qs, alias, model._meta.pk.column, Occurrence, 'object_id')
        rule_field = Occurrence._meta.get_field('rule')
        rule_alias = self._join(qs, occ_alias, rule_field.column, Rule, Rule._meta.pk)
        ct_field = Rule._meta.get_field('table')
        qs.query.where.add((Constraint(rule_alias, ct_field.column, ct_field), 'exact', ct.pk), AND)
        occ_qs = self.query
        if occ_qs.where:
            w = deepcopy(occ_qs.where)
            cmap = {}
            old_occ_alias, created = occ_qs.table_alias(Occurrence._meta.db_table)
            if not created and old_occ_alias != occ_alias:
                cmap[old_occ_alias] = occ_alias
            old_rule_alias, created = occ_qs.table_alias(Rule._meta.db_table)
            if not created and old_rule_alias != rule_alias:
                cmap[old_rule_alias] = rule_alias
            if cmap:
                w.relabel_aliases(cmap)
            qs.query.where.add(w, AND)
        return list(qs)

    @staticmethod
    def _join(qs, alias, lhs_col, model, field):
        if hasattr(field, 'column'):
            rhs_col = field.column
        else:
            rhs_col = model._meta.get_field(field).column
        return qs.query.join((alias, model._meta.db_table, lhs_col, rhs_col))


class OccurrenceManager(OccQueryMixin, models.Manager):
    def get_query_set(self):
        return OccurrenceSet(self.model, using=self._db)

    def create_for_rules(self, user, obj, rules=None, old_obj=None, product_id=None):
        if rules is None:
            table = ContentType.objects.get_for_model(type(obj))
            rules = Rule.objects.filter(table=table)
            if product_id:
                rules = rules.filter(product_id=product_id)
            else:
                rules = rules.filter(product__isnull=True)
        matches = rules.matches(old_obj, obj, product_id)

        # Serialize it just once
        old_obj = Occurrence(old_object=old_obj).old_obj
        self.bulk_create(
            [Occurrence(object_id=obj.pk, rule=rule, user=user, old_obj=old_obj) for rule in matches]
        )

    def try_resolve(self, user, obj):
        unresolved = self.unresolved_for_object(obj).select_related('rule', 'rule__table')
        still = []
        checked = []
        for occ in unresolved:
            occ.object = obj
            if not occ.try_resolve(user, save=False):
                still.append(occ.pk)
            checked.append(occ.rule.pk)
        resolved = unresolved.exclude(pk__in=still)
        resolved.update(resolution_date=timezone.now(), resolved_by=user, resolution_message='automatic')
        return checked


class Occurrence(models.Model):
    rule = models.ForeignKey(Rule)
    object_id = models.IntegerField()
    user = models.ForeignKey(User)
    old_obj = JSONTextField(blank=True, default='')
    creation_date = models.DateTimeField(auto_now_add=True)
    resolution_date = models.DateTimeField(blank=True, null=True)
    resolved_by = models.ForeignKey(User, blank=True, null=True, related_name='occurrences_resolved')
    resolution_message = models.CharField(max_length=100, blank=True, default='')
    # Link to reversion tables? At least for edits, a link to the old data so the caller doesn't
    # have to provide it...

    @property
    def object(self):
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
        if self.rule.when == 'delete':
            match = self.rule.match(self.object, None)
        else:
            match = self.rule.match(self.old_object, self.object)
        # If this rule, which was previously a match, is now not a match, the occurrence has been resolved
        if not match:
            self.resolve(user, 'automatic', save=save)
        return not match

    def resolve(self, user, message, save=True):
        self.resolution_date = timezone.now()
        self.resolved_by = user
        self.resolution_message = message
        if save:
            self.save()
