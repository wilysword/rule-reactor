import copy
import logging
import operator

from django.utils import tree

from .deferred import DeferredValue, ChainError

logger = logging.getLogger(__name__)

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

    def add(self, node, conn_type, *args, **kwargs):
        # Future Django versions did away with this bit, not sure why.
        if len(self.children) < 2:
            self.connector = conn_type
        return tree.Node.add(self, node, conn_type, *args, **kwargs)

    def negate(self):
        # !(x & y & z) = (!x | !y | !z)
        connector = AND if self.connector == OR else OR
        for c in self.children:
            c.negate()
        self.children = [self._new_instance(self.children, connector)]
        self.connector = self.default

    def collapse(self):
        """
        Removes unnecessary nodes, returning the minimum version of this tree.
        """
        children = self.children
        if len(children) > 0:
            i = 0
            while i < len(children):
                if isinstance(children[i], ConditionNode):
                    c = children[i]
                    c.collapse()
                    if len(c.children) < 2 or c.connector == self.connector:
                        children.pop(i)
                        children.extend(c.children)
                        continue
                i += 1
        if len(children) == 1 and isinstance(children[0], ConditionNode):
            self.children = children[0].children
            self.connector = children[0].connector

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

    # Order doesn't matter in boolean logic (unless you're short-circuiting).
    __rand__ = __and__
    __ror__ = __or__

    def __iand__(self, other):
        self.add(other, AND)
        return self

    def __ior__(self, other):
        self.add(other, OR)
        return self


class _unary_descriptor(object):
    def __get__(self, instance, owner):
        UOPS = owner.UNARY_OPERATORS
        if instance is not None:
            return instance.operator in UOPS
        return lambda operator: operator in UOPS
    __slots__ = ()


def _exists(left, right):
    try:
        # Efficiency improvement for querysets.
        return left.exists()
    except AttributeError:
        return bool(left)


def _like(left, right):
    return right.match(left)


class Condition(object):
    NEGATED_OPERATORS = {'not like': 'like',
                         'does not exist': 'exists',
                         'not in': 'in'}
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

    Node = ConditionNode

    @classmethod
    def C(cls, *args):
        conditions = []
        for a in args:
            if isinstance(a, dict):
                conditions.append(cls(**a))
            else:
                conditions.append(a)
        return cls.Node(conditions)

    is_unary = _unary_descriptor()

    def __init__(self, left, operator, right=None, negated=False):
        self.negated = bool(negated)
        if operator in self.NEGATED_OPERATORS:
            self.negate()
            operator = self.NEGATED_OPERATORS[operator]
        self.operator = operator
        self._eval = self.OPERATOR_MAP[operator]

        self.left = left
        self.right = right

    def __str__(self):
        fmt = '{} {}'
        if self.negated:
            fmt = 'NOT ' + fmt
        if not self.is_unary:
            fmt += ' {}'
        return fmt.format(self.left, self.operator, self.right)

    def negate(self):
        self.negated = not self.negated

    def evaluate(self, *objects, **extra):
        return self._evaluate({'objects': objects, 'extra': extra})

    def _evaluate(self, info):
        try:
            try:
                left = self.left.get_value(info)
                right = self.right and self.right.get_value(info)
            except ChainError:
                # A chain error with bool operator is as if the value is None.
                if not self.is_unary:
                    raise
                result = False
            else:
                result = self._eval(left, right)
                if result is NotImplemented:  # pragma: no cover
                    return False
            return not result if self.negated else bool(result)
        except:
            logger.debug('Exception while evaluating condition "{}"'
                         .format(self), exc_info=True)
            return False


class Rule(object):
    def __init__(self, trigger, **kwargs):
        self.trigger = trigger
        self.value = kwargs.get('value')
        self.conditions = self._build_tree(kwargs.get('conditions'))
        self.continuation = kwargs.get('continuation')
        if 'weight' in kwargs:
            self.weight = kwargs['weight']

    def _build_tree(self, conditions):
        if hasattr(conditions, '_evaluate'):
            return conditions
        elif not conditions:
            # Make it so the rule is never matched.
            return ConditionNode(connector=OR)
        else:
            # TODO parse
            return root

    def match(self, *objects, **extra):
        """Matches the given arguments against this rule."""
        return self._match({'objects': objects, 'extra': extra})
    __call__ = match

    def continue_(self, info, continuations):
        # Doesn't catch exceptions on purpose, so continuations can be
        # used to affect control flow (though that shouldn't be too common).
        cont = continuations[self.continuation]
        value = self.value
        if isinstance(value, DeferredValue):
            value = value.get_value(info)
        cont(self, info, value)

    def _match(self, info):
        try:
            if self.conditions._evaluate(info):
                return self
        except Exception:
            logger.debug('Exception while evaluating rule conditions for {}'
                         .format(self), exc_info=True)
        return False


def rule(trigger, **kwargs):
    def decorator(func):
        class conditions:
            @staticmethod
            def _evaluate(info):
                return func(*info['objects'], **info['extra'])
        kwargs['conditions'] = conditions
        r = Rule(trigger, **kwargs)
        if 'cache' in kwargs:
            kwargs['cache'].add_source(trigger, r)
        else:
            from .cache import RuleCache
            try:
                RuleCache.default.add_source(trigger, r)
            except AttributeError:
                from warnings import warn
                warn('Rule created but not added to any cache.')
        return r
    return decorator
