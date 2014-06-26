"""
Contains methods that implement the matching logic for each 'when' of rules.
"""
from django.contrib.contenttypes.models import ContentType


__all__ = ['exists_match', 'add_match', 'delete_match', 'edit_match', 'MATCHERS']


def _values(obj, values):
    return bool(obj) and all(map(lambda f: getattr(obj, f) in values[f], values))


def _check(obj, fields, values):
    return _values(obj, values) and all(map(lambda f: bool(getattr(obj, f)), fields))


def exists_match(rule, new_obj):
    """
    'exists' rules are matched the same way 'add' rules are, unless 'model' is present
    in the rule's ``condtions``.

    'model' should be a string like '<app_label>.<model_name>'. An additional key, 'filters',
    can be a dict containing arguments which will be passed to the model's ``filters`` method
    and checked for existance. As a special rule, any ``None`` values in the filters dict
    will be replaced with ``new_obj``, to allow checking relations.

    For example, if an 'exists' rule was attached to the :class:`~populations.models.Population`
    model with conditions like these::

        conditions = {'model': 'populations.individual', 'filters': {'population': None}}

    the rule would be triggered when a population that has individuals is saved.

    Note that 'not exists' is simply the negation of this method's result.
    """
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
    """
    'add' rules are met when a new object is created.

    Optional ``conditions`` keys 'new_values' and 'fields' can be used to restrict matches.
    'fields' is a list of fields which must have values in order to match the rule.
    'new_values' is a dict of <field_name>: list of values; the rule will only be matched if
    the given fields have values in the list.

    .. note::
        triggering a rule when a field is missing is slightly non-intuitive: you have to make
        a 'new_values' entry for the field with values list containing empty values for that
        field, e.g. [None, ''] for a CharField or [None, 0] for an IntegerField. To avoid
        conflicts with 'fields', which ensures existance, any keys in 'new_values' will be
        removed from 'fields' before the match is calculated.
    """
    values = rule.conditions.get('new_values', {})
    fields = set(rule.conditions.get('fields', ())) - set(values)
    return _check(new_obj, fields, values)


def delete_match(rule, old_obj):
    """Works just like :func:`add_match`, but with 'old_values' as the key instead of 'new_values'."""
    values = rule.conditions.get('old_values', {})
    fields = set(rule.conditions.get('fields', ())) - set(values)
    return _check(old_obj, fields, values)


def edit_match(rule, old_obj, new_obj):
    """
    Checks that an object was edited.

    ``conditions`` keys 'old_values' and 'new_values' work as in :func:`add_match` and
    :func:`delete_match`, respectively, but 'fields' works differently.

    If 'fields' is absent, the rule can only be matched if *any* fields have changed.
    If 'fields' is present, then the rule is only matched *all given* fields have changed.
    """
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
