from collections import defaultdict

__all__ = ['RuleList', 'RuleMutex', 'expand_key', 'RuleCache',
           'TopicalRuleCache']


def _sortkey(rule):
    return getattr(rule, 'weight', 0)


class RuleList(tuple):
    __slots__ = ()

    def __new__(cls, iterable=None):
        if iterable:
            return tuple.__new__(cls, sorted(iterable, key=_sortkey))
        return tuple.__new__(cls)

    def matches(self, *objects, **extra):
        return self._matches({'objects': objects, 'extra': extra})

    def _matches(self, info):
        results = []
        for r in self:
            x = r._match(info)
            if x:
                results.append(x)
        return results


class RuleMutex(tuple):
    __slots__ = ()
    __new__ = RuleList.__new__

    @property
    def weight(self):
        return _sortkey(self[0]) if self else 0

    def match(self, *objects, **extra):
        return self._match({'objects': objects, 'extra': extra})

    def _match(self, info):
        for r in self:
            x = r._match(info)
            if x:
                return x
        return False


def expand_key(key):
    parts = key.split('.')
    last = '#'
    keys = [key, last]
    for part in parts:
        last = last.replace('#', part + '.#')
        keys.append(last)
    return tuple(keys)


class sourcesdict(defaultdict):
    __slots__ = ('owner',)

    def __init__(self, owner):
        defaultdict.__init__(self)
        self.owner = owner

    def __missing__(self, key):
        r = self[key] = [self.owner.get_default_source(key)]
        return r


class RuleCache(defaultdict):
    __slots__ = ('source', 'sources')

    def __init__(self, source):
        self.source = source
        self.sources = sourcesdict(self)
        defaultdict.__init__(self)

    def add_source(self, key, source):
        self.sources[key].append(source)

    def get_default_source(self, key):
        return lambda c: self.source.filter(trigger=key)

    def set_primary_source(self, key, source):
        self.sources[key][0] = source

    def __missing__(self, key):
        rules = []
        for source in self.sources[key]:
            v = source
            if callable(source):
                v = source(self)
            if hasattr(v, '_match'):
                rules.append(v)
            else:
                rules.extend(v)
        self[key] = rules
        return self[key]

    def __setitem__(self, key, rules):
        if hasattr(rules, '_match'):
            rules = RuleList([rules])
        elif not hasattr(rules, '_matches'):
            rules = RuleList(rules)
        return defaultdict.__setitem__(self, key, rules)


class SourcelessCache(RuleCache):
    def __init__(self):
        super(SourcelessCache, self).__init__(lambda c: ())

    def get_default_source(self, key):
        return self.source


class TopicalRuleCache(RuleCache):
    __slots__ = ('expanders',)

    def __init__(self, source=None, expanders=None):
        if source is None:
            source = defaultdict(RuleList)
        self.expanders = expanders or []
        RuleCache.__init__(self, source)

    def _expandkey(self, key):
        for func in self.expanders:
            keys = func(key)
            if keys is not NotImplemented:
                return keys
        return expand_key(key)

    def get_default_source(self, key):
        def source(cache):
            keys = self._expandkey(key)
            result = []
            for k in keys:
                result.extend(self.source[k])
            return result

        return source

    def __delitem__(self, key):
        for k in self._expandkey(key):
            if k in self.source:
                del self.source[k]
        RuleCache.__delitem__(self, key)

    def clear(self):
        self.source.clear()
        RuleCache.clear(self)
