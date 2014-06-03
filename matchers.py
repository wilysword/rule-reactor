from django.contrib.contenttypes.models import ContentType


__all__ = ['exists_match', 'add_match', 'delete_match', 'edit_match', 'MATCHERS']


def _values(obj, values):
    return bool(obj) and all(map(lambda f: getattr(obj, f) in values[f], values))


def _check(obj, fields, values):
    return _values(obj, values) and all(map(lambda f: bool(getattr(obj, f)), fields))


#TODO consider child tables?
# e.g. you want the occurrence associated with a population member, but the rule is
# on 'add license'
# would you ever want that? maybe if you want a list of all members with errors?
# That could be another argument to put ContentType on Occurrence as well as Trigger
def exists_match(rule, new_obj):
    if 'model' in rule.conditions:
        app_label, name = rule.conditions['model'].split('.')
        model = ContentType.objects.get_by_natural_key(app_label, name).model_class()
        if model:
            filters = dict(rule.conditions.get('filters', {}))
            for k in filters:
                if filters[k] is None:
                    filters[k] = new_obj.pk if k.endswith('id') else new_obj
            return bool(new_obj) and model.objects.filter(**filters).exists()
    return add_match(rule, new_obj)


def add_match(rule, new_obj):
    values = rule.conditions.get('new_values', {})
    fields = set(rule.conditions.get('fields', ())) - set(values)
    return _check(new_obj, fields, values)


def delete_match(rule, old_obj):
    values = rule.conditions.get('old_values', {})
    fields = set(rule.conditions.get('fields', ())) - set(values)
    return _check(old_obj, fields, values)


def edit_match(rule, old_obj, new_obj):
    old_values = rule.conditions.get('old_values', {})
    new_values = rule.conditions.get('new_values', {})
    if 'fields' not in rule.conditions:
        fields = [f.attname for f in rule.table.model_class()._meta.fields]
        test = any
    else:
        fields = set(rule.conditions['fields'])
        test = all
    values = _values(old_obj, old_values) and _values(new_obj, new_values)
    return values and test(map(lambda f: getattr(old_obj, f) != getattr(new_obj, f), fields))


MATCHERS = {
    'add': lambda t, o, n: add_match(t, n),
    'edit': edit_match,
    'delete': lambda t, o, n: delete_match(t, o),
    'exists': lambda t, o, n: exists_match(t, n),
    'not exists': lambda t, o, n: not exists_match(t, n)
}
