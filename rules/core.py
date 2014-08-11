import copy
import operator

from django.utils import tree

from .continuations import ContinuationStore
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


class _unary_descriptor(object):
    __slots__ = ()
    def __get__(self, instance, owner):
        UOPS = owner.UNARY_OPERATORS
        if instance is not None:
            return instance.op in UOPS
        return lambda op: op in UOPS


def _exists(left, right):
    try:
        # Efficiency improvement for querysets.
        return left.exists()
    except AttributeError:
        return bool(left)


def _like(left, right):
    return right.match(left)


class Condition(object):
    NEGATED_OPERATORS = {'not like': 'like', 'does not exist': 'exists', 'not in': 'in'}
    UNARY_OPERATORS = {'bool', 'exists', 'does not exist'}
    OPERATOR_MAP = {
        '==': operator.eq,
        '!=': operator.ne,
        '<=': operator.le,
        '<': operator.lt,
        '>=': operator.ge,
        '>': operator.gt,
        'like': _like,
        're': _like,
        'exists': _exists,
        'bool': _exists,
        'in': lambda l, r: l in r,
    }

    KWARGS = ('left', 'right', 'operator', 'negated')

    Node = ConditionNode

    @classmethod
    def C(cls, *args):
        conditions = []
        Node = cls.Node
        for a in args:
            if isinstance(a, dict):
                conditions.append(cls(**a))
            elif isinstance(a, cls) or isinstance(a, Node):
                conditions.append(a)
            else:
                raise ValueError('Invalid positional argument: {}'.format(repr(a)))
        return Node(conditions)

    is_unary = _unary_descriptor()

    def __init__(self, **kwargs):
        unknown = [k for k in kwargs if k not in self.KWARGS]
        if unknown:
            raise TypeError('{} are invalid keyword arguments for this function'.format(unknown))
        self.negated = bool(kwargs.get('negated'))

        operator = kwargs.get('operator')
        if operator in self.NEGATED_OPERATORS:
            self.negate()
            operator = self.NEGATED_OPERATORS[operator]
        elif operator not in self.OPERATOR_MAP:
            raise NotImplementedError('Unknown operator: "{}"'.format(operator))
        self.op = operator
        self._eval = self.OPERATOR_MAP[operator]

        left = kwargs.get('left')
        right = kwargs.get('right')
        if not isinstance(left, DeferredValue):
            raise ValueError('Condition.left must be a deferred value type')
        if not self.is_unary and not right:
            msg = 'Condition.right is required unless using a unary operator.'
            raise ValueError(msg)
        elif right and not isinstance(right, DeferredValue):
            raise ValueError('Condition.right must be a deferred value type')
        self.left = left.maybe_const()
        self.right = right and right.maybe_const()

    def __str__(self):
        fmt = '{} {}'
        if self.negated:
            fmt = 'NOT ' + fmt
        if not self.is_unary:
            fmt += ' {}'
        return fmt.format(self.left, self.op, self.right)

    def negate(self):
        self.negated = not self.negated

    def evaluate(self, *objects, **extra):
        return self._evaluate({'objects': objects, 'extra': extra})

    def _evaluate(self, info):
        try:
            try:
                left = self.left
                if isinstance(left, DeferredValue):
                    left = left.get_value(info)
                right = self.right
                if isinstance(self.right, DeferredValue):
                    right = right.get_value(info)
            except ChainError:
                # A chain error with bool operator is assumed to mean the value is None.
                if not self.is_unary:
                    raise
                result = False
            else:
                result = self._eval(left, right)
                if result is NotImplemented:  # pragma: no cover
                    msg = 'Comparing {} and {} with {} operator'
                    raise NotImplementedError(msg.format(type(left), type(right), self.op))
            return not result if self.negated else bool(result)
        except:
            return False


class Rule(object):
    Condition = Condition
    continuations = ContinuationStore.default

    def __init__(self, **kwargs):
        self.value = kwargs.pop('value', None)
        self.conditions = self._build_tree(kwargs.pop('conditions', None))
        self.continuation = kwargs.pop('continuation', None)
        if 'Condition' in kwargs:
            self.Condition = kwargs.pop('Condition')
        if 'continuations' in kwargs:
            self.continuations = kwargs.pop('continuations')

    def _build_tree(self, conditions):
        Node = self.Condition.Node
        if isinstance(conditions, Node):
            return conditions
        elif not conditions:
            # Make it so the rule is never matched.
            return Node(connector=OR)
        else:
            # TODO parse
            return root

    def match(self, *objects, **extra):
        """Matches the given arguments against this rule."""
        return self._match({'objects': objects, 'extra': extra})

    def _match(self, info):
        if self.conditions._evaluate(info):
            store = info.get('continuations') or self.continuations
            cont = store[self.continuation]
            cont(self, info, self.value)
            return True
        return False
