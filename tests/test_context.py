import copy

from django.contrib.contenttypes.models import ContentType
from django.test import TestCase
from django.utils.timezone import now
from model_mommy import mommy, recipe

from falcon.core.models import Customer, User, Product
from populations.models import Population, Individual
from rule_reactor.models import Rule, Occurrence
from rule_reactor.context import RuleChecker

Customer = recipe.Recipe(Customer, inactive_date=now)
User = recipe.Recipe(User, customer=recipe.foreign_key(Customer), password_updated_on=now,
                     temp_password_expires_on=now, date_modified=now, inactive_date=now,
                     last_login_date=now, user_type_id=7)  # 7 == customer user
Product = recipe.Recipe(Product)


class TestRuleChecker(TestCase):
    def setUp(self):
        pop = mommy.make(Population, customer=Customer.make())
        self.user = User.make(customer=pop.customer)
        self.cti = ContentType.objects.get_for_model(Individual)
        ctp = ContentType.objects.get_for_model(Population)
        rule = recipe.Recipe(Rule, table=self.cti, type='error')
        self.rule1 = rule.make(when='add', conditions={'new_values': {'first_name': ['']}})
        self.rule2 = rule.make(when='edit', conditions={'fields': ['ssn'], 'new_values': {'ssn': [None, '']}})
        self.rule3 = rule.make(when='edit', customer=self.user.customer, type='warn')
        self.rule4 = rule.make(when='exists', table=ctp)
        self.rule5 = rule.make(product=Product.make())
        self.i = recipe.Recipe(Individual, population=pop)
        self.occ = recipe.Recipe(Occurrence, user=self.user)

    def test_init(self):
        self.assertRaises(ValueError, RuleChecker, None)
        rc = RuleChecker(self.user)
        self.assertEqual(len(rc.rules), 4)
        self.assertEqual(rc.models, frozenset((Individual, Population)))
        self.assertIs(rc.user, self.user)
        self.assertEqual(rc.objects, {})
        self.assertEqual(rc.errors, [])
        self.assertEqual(rc.warnings, [])
        self.assertEqual(rc.occurrences, [])

    def test_init_models(self):
        rc = RuleChecker(self.user, Individual)
        self.assertEqual(len(rc.rules), 3)

    def test_init_customer(self):
        rc = RuleChecker(self.user, customer=2)
        print([r.product_id for r in rc.rules])
        self.assertEqual(len(rc.rules), 3)
        self.user.is_superuser = True
        rc = RuleChecker(self.user)
        self.assertEqual(len(rc.rules), 3)

    def test_init_options(self):
        rc = RuleChecker(self.user)
        self.assertTrue(rc.save_occurrences)
        self.assertFalse(rc.need_pks)
        rc = RuleChecker(self.user, save_occurrences=False, need_pks=True)
        self.assertFalse(rc.save_occurrences)
        self.assertTrue(rc.need_pks)

    def test_init_rules(self):
        rc = RuleChecker(self.user, rules=Rule.objects.filter(pk=self.rule4.pk))
        self.assertEqual(rc.models, frozenset((Population,)))
        self.assertEqual(len(rc.rules), 1)

    def test_init_filters(self):
        rc = RuleChecker(self.user, when__in=('edit', 'exists'))
        self.assertEqual(len(rc.rules), 3)
        rc = RuleChecker(self.user, when='edit', type='warn')
        self.assertEqual(len(rc.rules), 1)

    def test_add_save_pk(self):
        with RuleChecker(self.user, Individual, need_pks=True) as rc:
            i = self.i.make(first_name='')
            self.assertEqual(len(rc.objects), 0)
            self.assertEqual(len(rc.occurrences), 1)
            self.assertEqual(len(rc.errors), 1)
            self.assertEqual(Occurrence.objects.count(), 1)
            self.assertIsNot(rc.occurrences[0].pk, None)
        self.assertEqual(Occurrence.objects.count(), 1)

    def test_add_save(self):
        with RuleChecker(self.user, Individual) as rc:
            i = self.i.make(first_name='')
            self.assertEqual(len(rc.objects), 0)
            self.assertEqual(len(rc.occurrences), 1)
            self.assertEqual(len(rc.errors), 1)
            self.assertEqual(Occurrence.objects.count(), 0)
            self.assertIs(rc.occurrences[0].pk, None)
        self.assertEqual(Occurrence.objects.count(), 1)
        self.assertIs(rc.occurrences[0].pk, None)

    def test_add_nosave(self):
        with RuleChecker(self.user, Individual, save_occurrences=False) as rc:
            i = self.i.make(first_name='')
            self.assertEqual(len(rc.objects), 0)
        self.assertEqual(len(rc.occurrences), 1)
        self.assertEqual(len(rc.errors), 1)
        self.assertEqual(Occurrence.objects.count(), 0)
        self.assertIs(rc.occurrences[0].pk, None)

    def test_edit_manual(self):
        i = self.i.make()
        with RuleChecker(self.user, Individual) as rc:
            self.assertEqual(len(rc.objects), 0)
            rc.track(i)
            self.assertEqual(len(rc.objects), 1)
            self.assertIn((Individual, i.pk), rc.objects)
            i.first_name = 'Glen'
            self.assertEqual(len(rc.occurrences), 0)
            i.save()
            self.assertEqual(len(rc.occurrences), 1)
            self.assertEqual(len(rc.errors), 0)
            self.assertEqual(len(rc.warnings), 1)
            self.assertEqual(Occurrence.objects.count(), 0)
        self.assertEqual(Occurrence.objects.count(), 1)

    def test_edit_automatic(self):
        self.i.make()
        with RuleChecker(self.user, Individual) as rc:
            i = Individual.objects.get()
            self.assertEqual(len(rc.objects), 1)
            self.assertIn((Individual, i.pk), rc.objects)
            i.first_name = 'Glen'
            self.assertEqual(len(rc.occurrences), 0)
            i.save()
            self.assertEqual(len(rc.occurrences), 1)
            self.assertEqual(len(rc.errors), 0)
            self.assertEqual(len(rc.warnings), 1)
            self.assertEqual(Occurrence.objects.count(), 0)
        self.assertEqual(Occurrence.objects.count(), 1)
