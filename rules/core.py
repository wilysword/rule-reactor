import copy

from django.utils import tree

from .deferred import DeferredValue, ChainError

__all__ = ['AND', 'OR', 'ConditionNode', 'Condition']

AND = 'AND'
OR = 'OR'


class ConditionNode(tree.Node):
    default = AND

    def evaluate(self, *objects, **extra):
        return self._evaluate({'objects': objects, 'extra': extra})

    def _evaluate(self, info):
        test = all if self.connector == AND else any
        return test(child._evaluate(info) for child in self.children)

    def negate(self):
        # !(x & y & z) = (!x | !y | !z)
        connector = AND if self.connector == OR else OR
        for c in self.children:
            c.negate()
        self.children = [self._new_instance(self.children, connector)]
        self.connector = self.default

    def collapse(self):
        """Removes unnecessary nodes, returning the minimum number of nodes for this tree."""
        c = self.children
        if len(c) > 0:
            i = 0
            while i < len(c):
                if isinstance(c[i], ConditionNode):
                    child = c[i]
                    child.collapse()
                    if len(child.children) < 2 or child.connector == self.connector:
                        c.pop(i)
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
        return ored.__ior__(other)

    # Order doesn't matter in boolean logic (assuming you aren't relying on short-circuiting).
    __rand__ = __and__
    __ror__ = __or__

    def __iand__(self, other):
        self.add(other, AND)
        return self

    def __ior__(self, other):
        self.add(other, OR)
        return self


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

    KWARGS = ('left', 'right', 'operator', 'negated')

    @classmethod
    def C(cls, *args):
        conditions = []
        for a in args:
            if isinstance(a, dict):
                conditions.append(cls(**a))
            elif isinstance(a, cls) or isinstance(a, ConditionNode):
                conditions.append(a)
            else:
                raise ValueError('Invalid positional argument: {}'.format(repr(a)))
        return ConditionNode(conditions)

    @classmethod
    def is_unary(cls, operator):
        return operator in ('bool', 'exists', 'does not exist')

    def __init__(self, **kwargs):
        unknown = [repr(k) for k in kwargs if k not in self.KWARGS]
        if unknown:
            raise TypeError('{} are invalid keyword arguments for this function'.format(unknown))
        if not isinstance(kwargs.get('left'), DeferredValue):
            raise ValueError('Condition.left must be a deferred value type')
        self.left = kwargs['left']
        self.negated = bool(kwargs.get('negated'))
        operator = kwargs['operator']
        if operator in self.NEGATED_OPERATOR_MAP:
            self.negate()
        if operator in self.OPERATOR_MAP:
            self.operator = self.OPERATOR_MAP[operator]
        elif operator in self.OPERATOR_MAP.values():
            self.operator = operator
        else:
            raise NotImplementedError('Unknown operator: "{}"'.format(operator))
        right = kwargs.get('right') or ''
        if self.operator != 'bool' and not right:
            msg = 'Condition.right is required unless using the bool/exists operator.'
            raise ValueError(msg)
        elif not isinstance(right, DeferredValue):
            raise ValueError('Condition.right must be a deferred value type')
        self.right = right

    def __str__(self):
        fmt = '{} {}'
        if self.negated:
            fmt = 'NOT ' + fmt
        if self.right:
            fmt += ' {}'
        return fmt.format(self.left, self.operator, self.right)

    def negate(self):
        self.negated = not self.negated

    def _eval(self, left, right):
        if self.operator == '==':
            result = left == right
        elif self.operator == 're':
            # Reversed operands to reflect the semantic: <left> like pattern <right>.
            result = bool(right.match(left))
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
        return self._evaluate({'objects': objects, 'extra': extra})

    def _evaluate(self, info):
        try:
            try:
                left = self.left.get_value(info)
                right = None
                if self.right:
                    right = self.right.get_value(info)
            except ChainError:
                if self.operator == 'bool':
                    return not self.negated
            result = self._eval(left, right)
            return not result if self.negated else result
        except:
            return False
