from django.db.models.sql.where import AND, OR
from django.utils import tree


class ConditionNode(tree.Node):
    default = AND

    def add(self, node, conn_type):
        if len(self.children) >= 1 and conn_type != self.connector:
            raise ValueError('Mismatched connectors adding {} to {}'.format(node, self))
        super(ConditionNode, self).add(node, conn_type)

    def evaluate(self, old_obj, new_obj, extra):
        test = all if self.connector == AND else any
        return test(child.evaluate(old_obj, new_obj, extra) for child in children)

    def save(self, parent=None):
        # TODO turn this tree into rows in the database
        pass


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
