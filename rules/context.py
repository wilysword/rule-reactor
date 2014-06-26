from copy import deepcopy

from django.db.models.signals import post_init, post_save, post_delete

from .models import Rule, Occurrence


class RuleChecker(object):
    """
    Allows automatic rule-checking on rules that aren't associated with products.

    To use, simply instantiate in a with statement::
        with RuleChecker(request.user) as rc:

    For edits to work properly, objects must be instantiated (including by evaluating a query)
    and saved within the ``with`` block. If they must be instantiated outside, rules can still be
    applied automatically by calling :meth:`track` on each object before saving it.

    As the RuleChecker depends on signals, it will not work with methods like ``QuerySet.update``,
    since those bulk operations do not send signals.
    """

    def __init__(self, user, *models, **kwargs):
        """
        :param user: The current user, usually taken from ``request.user``.
        :type user: A user-like object with ``pk`` and ``is_superuser`` attributes.
        :param models: An optional list of Model classes for which to register signals.
        :param kwargs: Other optional arguments:
            * ``save_occurrences`` (True) Whether created occurrences should be saved automatically.
            * ``need_pks`` (False) True if the surrounding code need PKs on the created occurrences,
              as to create URLs to the occurrence resolution page. Otherwise, ``bulk_create`` is used.
            * ``customer`` (user.customer) The customer whose rules we'll check (system rules are
              always checked). If not provided and user is a superuser, only system rules are checked.
            * ``rules`` (None) If the rules to be checked cannot be retrieved with a simple query,
              they can be passed in via the ``rules`` option. All other parameters (besides ``user``)
              are unnecessary if this option is used. Note that this must have the
              :meth:`rule_reactor.models.RuleSet.matches` method, so it cannot be a list or tuple.
            * Any other keyword args are passed as-is to ``Rule.objects.filter`` to generate the rules
              queryset (assuming ``rules`` was not passed as an option).
        """
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
        """Add an object to tracking so that edits can be properly distinguished from adds."""
        if type(obj) not in self.models:
            raise TypeError('This checker can only track objects of the following types: ' +
                            ', '.join(m.__name__ for m in self.models))
        self._track(instance=obj, sender=type(obj))

    def _track(self, **kwargs):
        obj = kwargs['instance']
        if obj.pk:
            self.objects[(kwargs['sender'], obj.pk)] = deepcopy(obj)

    def _check_rules(self, old_obj, new_obj):
        # TODO should this also automatically do try_resolve, or should that be left at the discretion of the caller?
        matches = self.rules.matches(old_obj, new_obj)
        for rule in matches:
            oid = new_obj.pk if new_obj else 0
            occ = Occurrence(object=new_obj, old_object=old_obj, rule=rule, user_id=self.user.pk)
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
        """
        Connects signals so the RuleChecker will know when to check rules and whether the
        action is an add, edit or delete.
        """
        for model in self.models:
            post_init.connect(self._track, sender=model, dispatch_uid='track{}'.format(id(self)))
            post_save.connect(self._check, sender=model, dispatch_uid='check{}'.format(id(self)))
            post_delete.connect(self._check_delete, sender=model, dispatch_uid='cdel{}'.format(id(self)))
        return self

    def __exit__(self, *exc_info):
        """Disconnects signals and bulk creates occurrences, if their PKs aren't needed."""
        for model in self.models:
            post_init.disconnect(dispatch_uid='track{}'.format(id(self)), sender=model)
            post_save.disconnect(dispatch_uid='check{}'.format(id(self)), sender=model)
            post_delete.disconnect(sender=model, dispatch_uid='cdel{}'.format(id(self)))
        if self.save_occurrences and not self.need_pks and self.occurrences:
            Occurrence.objects.bulk_create(self.occurrences)
