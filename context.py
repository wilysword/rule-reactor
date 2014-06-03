from copy import deepcopy

from django.db.models.signals import post_init, post_save, post_delete

from .models import Rule, Occurrence


class RuleChecker(object):
    def __init__(self, user, *models, **kwargs):
        if not user:
            raise ValueError('Occurrences must be associated with a user')
        rules = kwargs.pop('rules', None)
        self.save_occurrences = kwargs.pop('save_occurrences', True)
        self.need_pks = kwargs.pop('need_pks', False)
        customer = kwargs.pop('customer', None if user.is_superuser else user.customer_id)
        if not rules:
            kwargs['product__isnull'] = True
            rules = Rule.objects.filter(**kwargs)
            if models:
                rules = rules.for_models(*models)
            if customer:
                rules = rules.for_customer(customer)
            else:
                rules = rules.system()
        if not models:
            models = (r.table.model_class() for r in rules)
        self.rules = rules
        self.models = frozenset(models)
        self.user = user
        self.objects = {}
        self.errors = []
        self.warnings = []
        self.occurrences = []

    def track(self, obj):
        if type(obj) not in self.models:
            raise TypeError('This checker can only track objects of the following types: ' +
                            ', '.join(m.__name__ for m in self.models))
        self._track(instance=obj, sender=type(obj))

    def _track(self, **kwargs):
        obj = kwargs['instance']
        if obj.pk:
            self.objects[(kwargs['sender'], obj.pk)] = deepcopy(obj)

    def _check_rules(self, old_obj, new_obj):
        matches = self.rules.matches(old_obj, new_obj)
        for rule in matches:
            oid = new_obj.pk if new_obj else 0
            occ = Occurrence(object=new_obj, old_object=old_obj, rule=rule, user=self.user)
            self.occurrences.append(occ)
            if rule.type == 'error':
                self.errors.append(occ)
            elif rule.type == 'warn':
                self.warnings.append(occ)
            if self.save_occurrences and self.need_pks:
                occ.save()

    def _check(self, **kwargs):
        new_obj = kwargs['instance']
        old_obj = self.objects.get((kwargs['sender'], new_obj.pk))
        self._check_rules(old_obj, new_obj)

    def _check_delete(self, **kwargs):
        old_obj = kwargs['instance']
        self._check_rules(old_obj, None)

    def __enter__(self):
        for model in self.models:
            post_init.connect(self._track, sender=model, dispatch_uid='track{}'.format(id(self)))
            post_save.connect(self._check, sender=model, dispatch_uid='check{}'.format(id(self)))
            post_delete.connect(self._check_delete, sender=model, dispatch_uid='cdel{}'.format(id(self)))
        return self

    def __exit__(self, *exc_info):
        for model in self.models:
            post_init.disconnect(dispatch_uid='track{}'.format(id(self)), sender=model)
            post_save.disconnect(dispatch_uid='check{}'.format(id(self)), sender=model)
            post_delete.disconnect(sender=model, dispatch_uid='cdel{}'.format(id(self)))
        if self.save_occurrences and not self.need_pks and self.occurrences:
            Occurrence.objects.bulk_create(self.occurrences)
