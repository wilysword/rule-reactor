import copy
import re
from django.utils import tree
from django.contrib.contenttypes.models import ContentType

AND = 'AND'
OR = 'OR'


class ConditionNode(tree.Node):
    default = AND

    def _add(self, node, conn_type):
        """
        This version of add is intended for constructing a condition tree from a data
        source (e.g. the database); thus, it adds validation on the connector.
        """
        if len(self.children) >= 1 and conn_type != self.connector:
            raise ValueError('Mismatched connectors adding {} to {}'.format(node, self))
        self.add(node, conn_type)

    def evaluate(self, *objects, **extra):
        return self._evaluate(objects, extra)

    def _evaluate(self, objects, extra):
        test = all if self.connector == AND else any
        return test(child._evaluate(objects, extra) for child in children)

    def negate(self):
        # !(x & y & z) = (!x | !y | !z)
        connector = AND if self.connector == OR else OR
        for c in self.children:
            c.negate()
        self.children = [self._new_instance(self.children, connector)]
        self.connector = default

    def collapse(self):
        """Removes unnecessary nodes, returning the minimum number of nodes for this tree."""
        c = self.children
        if len(self.children) > 0:
            i = 0
            while i < len(c):
                if isinstance(c[i], ConditionNode):
                    child = c[i]
                    child.collapse()
                    if len(child.children) == 0 or child.connector == self.connector:
                        children.pop(i)
                        c.extend(child.children)
                        continue
                i += 1
        if len(c) == 1 and isinstance(c[0], ConditionNode):
            self.children = c[0].children
            self.connector = c[0].connector

    def __invert__(self):
        negated = copy.deepcopy(self)
        negated.negate()
        return negated

    def __and__(self, other):
        anded = copy.deepcopy(self)
        return anded.__iand__(other)

    def __or__(self, other):
        ored = copy.deepcopy(self)
        return order.__ior__(other)

    def __iand__(self, other):
        self.add(other, AND)
        return self

    def __ior__(self, other):
        self.add(other, OR)
        return self


def get_value(obj, chain, i=0):
    if i >= len(chain) or obj is None:
        return obj
    elif not chain[i]:
        nobj = lambda: obj
    elif isinstance(obj, dict):
        nobj = obj.get(chain[i])
    else:
        nobj = getattr(obj, chain[i], None)
    return get_value(nobj() if callable(nobj) else nobj, chain, i + 1)


class Condition(object):
    NEGATED_OPERATOR_MAP = {
        '!=': '==',
        'not like': 're',
        '>': '<=',
        '>=': '<',
        'does not exist': 'bool',
        'not in': 'in'
    }
    OPERATOR_MAP = {
        '==': '==',
        'like': 're',
        'exists': 'bool',
        '<=': '<=',
        '<': '<',
        'in': 'in'
    }
    OPERATOR_MAP.update(NEGATED_OPERATOR_MAP)

    KWARGS = ('left', 'right', 'operator', 'negated', 'value')
    KWARG_OP_MAP = {
        'lt': '<',
        'lte': '<=',
        'gt': '>',
        'gte': '>=',
        'exists': 'bool',
        'like': 're',
        'in': 'in'
    }

    @classmethod
    def parse_kwarg(cls, key, value):
        result = {'right': 'const', 'value': value}
        parts = key.split('__')
        if parts[0].startswith('o'):
            parts[0] = parts[0].strip('o')
            assert parts[0].isdigit()
        else:
            parts.insert(0, 'extra')
        if parts[-1] in cls.KWARG_OP_MAP:
            result['operator'] = cls.KWARG_OP_MAP[parts.pop()]
        else:
            result['operator'] = '=='
        result['left'] = '.'.join(parts)
        return result

    @classmethod
    def parse_kwargs(cls, kwargs):
        results = []
        result = {}
        for key in kwargs:
            if key in cls.KWARGS:
                result[key] = kwargs[key]
            else:
                results.append(cls.parse_kwarg(key, kwargs[key]))
        if result:
            results.append(result)
        return results

    @classmethod
    def C(cls, *args, **kwargs):
        conditions = []
        for a in args:
            if isinstance(a, dict):
                a = cls.parse_kwargs(a)
                conditions.extend(cls(**arg) for arg in a)
            elif isinstance(a, cls) or isinstance(a, ConditionNode):
                conditions.append(a)
            else:
                raise ValueError('Invalid positional argument: {}'.format(a))
        args = cls.parse_kwargs(kwargs)
        conditions.extend(cls(**a) for a in args)
        return ConditionNode(conditions)

    def __init__(self, **kwargs):
        tmp = self.parse_kwargs(kwargs)
        if len(tmp) != 1:
            raise TypeError('Missing all arguments')
        kwargs = tmp[0]
        operator = kwargs['operator']
        self.left = kwargs['left']
        right = kwargs.get('right') or ''
        self.negated = kwargs.get('negated') or False
        if operator in self.NEGATED_OPERATOR_MAP:
            self.negate()
        if operator in self.OPERATOR_MAP:
            self.operator = self.OPERATOR_MAP[operator]
        elif operator in self.OPERATOR_MAP.values():
            self.operator = operator
        else:
            raise NotImplementedError('Unknown operator: "{}"'.format(operator))
        if self.operator != 'bool' and not right:
            msg = 'The right-hand selector is required unless using the bool/exists operator.'
            raise ValueError(msg)
        self.right = re.compile(right, re.UNICODE) if self.operator == 're' else right
        self.value = kwargs.get('value') or ''

    def __str__(self):
        fmt = 'not ({} {} {}) with {}' if self.negated else '{} {} {} with {}'
        return fmt.format(self.left, self.operator, self.right, self.value)

    def negate(self):
        self.negated = not self.negated

    def value_as_dict(self):
        if isinstance(self.value, dict):
            return self.value
        raise NotImplementedError('Cannot convert {} to dict'.format(repr(self.value)))

    def _get_mod(self, model, extra):
        model = ContentType.objects.get_by_natural_key(*model).model_class()
        if self.value:
            filters = self.value_as_dict()
            for key, val in filters.items():
                if key in extra:
                    filters[key] = extra[key]
            return model.objects.filter(**filters)
        return model.objects.all()

    def _try_match_type(self, left, right):
        """Hook for derived classes, e.g. in case they store const values as strings."""
        return left, right

    def _eval(self, left, right):
        if self.operator == '==':
            result = left == right
        elif self.operator == 're':
            # Reversed operands to reflect the semantic: <left> like pattern <right>.
            result = bool(re.search(right, left))
        elif self.operator == '<':
            result = left < right
        elif self.operator == '<=':
            result = left <= right
        elif self.operator == 'in':
            result = left in right
        elif self.operator == 'bool':
            try:
                # Efficiency improvement for querysets.
                result = left.exists()
            except AttributeError:
                result = bool(left)
        else:
            raise NotImplementedError('Comparison type {}'.format(self.operator))
        return result

    def evaluate(self, *objects, **extra):
        return self._evaluate(objects, extra)

    def _evaluate(self, objects, extra):
        left = get_value(*self._select(self.left, objects, extra))
        right = get_value(*self._select(self.right, objects, extra))
        left, right = self._try_match_type(left, right)
        result = self._eval(left, right)
        return not result if self.negated else result

    def _select(self, selector, objects, extra):
        s = selector.split('.')
        stype, field = s[0], s[1:]
        if stype.isdigit():
            obj = objects[int(stype)]
        elif stype == 'extra':
            obj = extra
        elif stype == 'const':
            obj = self.value
        elif stype == 'model':
            model, field = field[:2], field[2:]
            obj = self._get_mod(model, extra)
        else:
            raise NotImplementedError('Unknown selector type: "{}"'.format(stype))
        return obj, field


def ConditionTree(conditions):
    if isinstance(conditions, ConditionNode):
        return conditions
    if not conditions:
        return ConditionNode()
    ids = set(c.pk for c in conditions)
    pids = set(c.parent_id for c in conditions if c.parent_id)
    if pids - ids:
        raise ValueError('Missing parents: {}'.format(pids - ids))
    nodes = {c.pk: ConditionNode() for c in conditions if c.pk in pids}
    rule = None
    root = ConditionNode()
    for condition in conditions:
        if rule is None:
            rule = condition.rule_id
        elif rule != condition.rule_id:
            raise ValueError('All conditions in a tree must come from the same rule')
        parent = nodes.get(condition.parent_id, root)
        parent.add(condition, condition.connector)
        if condition.pk in nodes:
            parent.add(nodes[condition.pk], condition.connector)
    return root
