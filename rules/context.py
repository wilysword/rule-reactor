import logging
from copy import deepcopy

from django.db.models.signals import (
    post_init, pre_save, post_save, pre_delete, post_delete
)

from .cache import RuleCache, TopicalRuleCache
from .continuations import ContinuationStore, NoContinuationError

logger = logging.getLogger(__name__)


class RuleChecker(object):
    __slots__ = ('cache', 'context', '_cont', 'continuations')

    def __init__(self, **kwargs):
        cls = kwargs.get('cls') or TopicalRuleCache
        if 'cache' in kwargs:
            cache = kwargs.get('cache')
        elif 'rules' in kwargs:
            cache = cls()
            for r in kwargs['rules']:
                cache.add_source(r.trigger, r)
        elif 'queryset' in kwargs:
            cache = cls(RuleCache(kwargs['queryset']))
        elif 'source' in kwargs:
            cache = cls(kwargs['source'])
        elif hasattr(cls, 'default'):
            cache = cls.default
        else:
            raise ValueError('No rules, rule cache, or rule source provided.')
        used = {'cls', 'rules', 'cache', 'queryset', 'source',
                'context', 'continuations'}
        context = {k: kwargs[k] for k in kwargs if k not in used}
        context.update(kwargs.get('context', ()))
        self.context = context
        self.cache = cache
        self._cont = kwargs.get('continuations') or ContinuationStore.default

    def check(self, trigger, *objects, **extra):
        info = {'objects': objects, 'extra': extra}
        matches = self.cache[trigger]._matches(info)
        for rule in matches:
            try:
                rule.continue_(info, self.continuations)
            except NoContinuationError:
                logger.debug('Continuation not found', exc_info=True)
        return matches

    def __enter__(self):
        self.continuations = self._cont.bind(self.context)
        return self

    def __exit__(self, *exc_info):
        self.continuations.unbind()
        del self.continuations


def check_rules(*args, **kwargs):
    if not args:
        return lambda func: check_rules(func, **kwargs)
    elif len(args) != 1 or not callable(args[0]):
        raise TypeError('Requires exactly one callable positional argument')
    func = args[0]
    rc = RuleChecker(**kwargs)

    @functools.wraps(func)
    def wrapper(request, *a, **k):
        with rc:
            request.rule_checker = rc
            return func(request, *a, **k)
    return wrapper


class SignalChecker(RuleChecker):
    __slots__ = ('user', 'models', 'objects')

    def __init__(self, user, *models, **kwargs):
        super(SignalChecker, self).__init__(**kwargs)
        self.user = user
        self.models = models
        self.objects = {}

    def track(self, obj):
        """
        Tracks an object so that edits can be properly distinguished from adds.
        """
        model = type(obj)
        is_tracked = any(issubclass(model, m) for m in self.models)
        if self.models and not is_tracked:
            msg = 'This checker only tracks objects of the following types: {}'
            model_names = ', '.join(m.__name__ for m in self.models)
            raise ValueError(msg.format(model_names))
        self._track(instance=obj, sender=model)

    def _track(self, **kwargs):
        obj = kwargs['instance']
        if obj.pk:
            self.objects[(kwargs['sender'], obj.pk)] = deepcopy(obj)

    def _get_trigger(self, eventtype, model, sig=None):
        m = model._meta.concrete_model._meta
        key = '{}.{}.{}'.format(eventtype, m.app_label, m.object_name.lower())
        if sig:
            key += ':' + sig
        return key

    def _check_update(self, sender, instance, sig=None):
        if instance.pk not in self.objects:
            # Can't check rules without sufficient info.
            return
        original = self.objects[instance.pk]
        trigger = self._get_trigger('update', sender, sig)
        self.check(trigger, original, instance, user=self.user)
        if not sig or 'post' in sig:
            self._track(sender=sender, instance=instance)

    def _check_create(self, sender, instance, sig=None):
        trigger = self._get_trigger('create', sender, sig)
        self.check(trigger, instance, user=self.user)
        if not sig or 'post' in sig:
            self._track(sender=sender, instance=instance)

    def _check_pres(self, sender, **kwargs):
        i = kwargs['instance']
        if i.pk:
            self._check_update(sender, i, 'pre_save')
        else:
            self._check_create(sender, i, 'pre_save')

    def _check_posts(self, sender, **kwargs):
        i = kwargs['instance']
        if kwargs['created']:
            self._check_create(sender, i)
        else:
            self._check_update(sender, i)

    def _check_pred(self, sender, **kwargs):
        i = kwargs['instance']
        trigger = self._get_trigger('delete', sender, 'pre_delete')
        self.check(trigger, i, user=self.user)

    def _check_postd(self, sender, **kwargs):
        i = kwargs['instance']
        trigger = self._get_trigger('delete', sender)
        self.check(trigger, i, user=self.user)
        if i.pk in self.objects:
            del self.objects[i.pk]

    def _connect(self, sender=None):
        post_init.connect(self._track, sender=sender)
        pre_save.connect(self._check_pres, sender=sender)
        post_save.connect(self._check_posts, sender=sender)
        pre_delete.connect(self._check_pred, sender=sender)
        post_delete.connect(self._check_postd, sender=sender)

    def _disconnect(self, sender=None):
        post_init.disconnect(self._track, sender=sender)
        pre_save.disconnect(self._check_pres, sender=sender)
        post_save.disconnect(self._check_posts, sender=sender)
        pre_delete.disconnect(self._check_pred, sender=sender)
        post_delete.disconnect(self._check_postd, sender=sender)

    def __enter__(self):
        """
        Connects signals so the RuleChecker will know when to check rules and
        whether the action is an add, edit or delete.
        """
        if self.models:
            for m in self.models:
                self._connect(m)
        else:
            self._connect()
        return super(SignalChecker, self).__enter__()

    def __exit__(self, *exc_info):
        """Disconnects signals."""
        if self.models:
            for m in self.models:
                self._disconnect(m)
        else:
            self._disconnect()
        super(SignalChecker, self).__exit__()


def check_signals(*args, **kwargs):
    if not args:
        return lambda func: check_signals(func, **kwargs)
    elif len(args) != 1 or not callable(args[0]):
        raise TypeError('Requires exactly one callable positional argument')
    func = args[0]
    models = kwargs.pop('models', None) or ()
    # Validate arguments using the constructor.
    sc = SignalChecker(None, *models, **kwargs)
    # Though we can't reuse the instance, we can reuse the cache.
    kwargs.setdefault('cache', sc.cache)

    @functools.wraps(func)
    def wrapper(request, *a, **k):
        with SignalChecker(request.user, *models, **kwargs) as sc:
            request.signal_checker = sc
            return func(request, *a, **k)
    return wrapper
