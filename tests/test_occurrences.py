import copy

from django.contrib.contenttypes.models import ContentType
from django.test import TestCase
from django.utils.timezone import now
from model_mommy import mommy, recipe

from falcon.core.models import Customer, User
from populations.models import Population, Individual
from rule_reactor.models import Rule, Occurrence

Customer = recipe.Recipe(Customer, inactive_date=now)
User = recipe.Recipe(User, customer=recipe.foreign_key(Customer), password_updated_on=now,
                     temp_password_expires_on=now, date_modified=now, inactive_date=now,
                     last_login_date=now, user_type_id=7)  # 7 == customer user


class TestOccurrence(TestCase):
    def setUp(self):
        pop = mommy.make(Population, customer=Customer.make())
        self.user = User.make(customer=pop.customer)
        self.cti = ContentType.objects.get_for_model(Individual)
        rule = recipe.Recipe(Rule, table=self.cti, type='error')
        self.rule1 = rule.make(when='add', conditions={'new_values': {'first_name': ['']}})
        self.rule2 = rule.make(when='edit', conditions={'new_values': {'ssn': [None, '']}})
        self.i = recipe.Recipe(Individual, population=pop)
        self.occ = recipe.Recipe(Occurrence, user=self.user)

    def test_try_resolve1(self):
        i = self.i.make(first_name='')
        self.assertTrue(self.rule1.match(None, i))
        occ = self.occ.make(object_id=i.pk, rule=self.rule1)
        self.assertFalse(occ.try_resolve(self.user))
        self.assertIs(occ.resolution_date, None)
        self.assertIs(occ.resolved_by, None)
        self.assertEqual(occ.resolution_message, '')
        occ.object.first_name = 'Glen'
        self.assertTrue(occ.try_resolve(self.user))
        self.assertIsNot(occ.resolution_date, None)
        self.assertEqual(occ.resolved_by.pk, self.user.pk)
        self.assertEqual(occ.resolution_message, 'automatic')

    def test_try_resolve2(self):
        i = self.i.make(ssn='200345444')
        occ = self.occ.make(object_id=i.pk, rule=self.rule2, old_object=i)
        occ.object.ssn = None
        self.assertTrue(self.rule2.match(occ.old_object, occ.object))
        self.assertFalse(occ.try_resolve(self.user))
        self.assertIs(occ.resolution_date, None)
        self.assertIs(occ.resolved_by, None)
        self.assertEqual(occ.resolution_message, '')
        occ.object.ssn = ''
        self.assertTrue(self.rule2.match(occ.old_object, occ.object))
        self.assertFalse(occ.try_resolve(self.user))
        occ.object.ssn = '999999999'
        self.assertTrue(occ.try_resolve(self.user))
        self.assertIsNot(occ.resolution_date, None)
        self.assertEqual(occ.resolved_by.pk, self.user.pk)
        self.assertEqual(occ.resolution_message, 'automatic')

    def test_resolve1(self):
        occ = self.occ.make(object_id=self.i.make().pk)
        occ.resolve(None, 'hello', save=False)
        self.assertNotEqual(occ.resolution_date, Occurrence.objects.get().resolution_date)
        self.assertIsNot(occ.resolution_date, None)
        self.assertIs(occ.resolved_by, None)
        self.assertEqual(occ.resolution_message, 'hello')

    def test_resolve2(self):
        occ = self.occ.make(object_id=self.i.make().pk)
        occ.resolve(self.user, 'hello')
        self.assertEqual(occ.resolution_date, Occurrence.objects.get().resolution_date)
        self.assertIsNot(occ.resolution_date, None)
        self.assertEqual(occ.resolved_by_id, self.user.pk)
        self.assertEqual(occ.resolution_message, 'hello')


class TestOccurrenceManager(TestCase):
    def setUp(self):
        self.pop = mommy.make(Population, customer=Customer.make())
        self.individuals = mommy.make(Individual, population=self.pop, _quantity=5)
        self.cti = ContentType.objects.get_for_model(Individual)

    def test_restrict(self):
        i = self.individuals[1]
        mommy.make(Occurrence, rule__type='error', rule__table=self.cti,
                   object_id=i.pk, user=User.make())
        iqs = Individual.objects.only('pk')
        self.assertEqual(iqs.count(), 5)
        individual = Occurrence.objects.all().restrict(iqs)
        self.assertEqual(len(individual), 1)

    def test_restrict_filters(self):
        i = self.individuals[1]
        mommy.make(Occurrence, rule__type='error', rule__table=self.cti,
                   object_id=i.pk, user=User.make())
        iqs = Individual.objects.only('pk')
        self.assertEqual(iqs.count(), 5)
        individual = Occurrence.objects.unresolved().filter(rule__type='error').restrict(iqs)
        self.assertEqual(len(individual), 1)

    def test_try_resolve(self):
        rule = recipe.Recipe(Rule, table=self.cti, type='error')
        rule1 = rule.make(when='add', conditions={'new_values': {'first_name': ['']}})
        user = User.make(customer=self.pop.customer)
        i = mommy.make(Individual, first_name='', population=self.pop)
        occ = mommy.make(Occurrence, user=user, object_id=i.pk, rule=rule1)
        Occurrence.objects.try_resolve(user, i)
        occ = Occurrence.objects.get()
        self.assertIs(occ.resolution_date, None)
        self.assertIs(occ.resolved_by, None)
        self.assertEqual(occ.resolution_message, '')
        i.first_name = 'Glen'
        i.save()
        Occurrence.objects.try_resolve(user, i)
        occ = Occurrence.objects.get()
        self.assertIsNot(occ.resolution_date, None)
        self.assertEqual(occ.resolved_by_id, user.pk)
        self.assertEqual(occ.resolution_message, 'automatic')
