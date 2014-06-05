from django.conf import settings
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


class TestView(TestCase):
    def setUp(self):
        USER = User.make()
        CUST = USER.customer
        self._original_session_engine = settings.SESSION_ENGINE
        settings.SESSION_ENGINE = 'django.contrib.sessions.backends.file'
        from django.contrib.sessions.backends import file
        from django.forms import model_to_dict
        self._engine = file
        self._user = model_to_dict(USER, exclude=('hashed_password',))
        self._user.update({
            'status': 'Authenticated',
            'last_login_date': USER.last_login_date,
            'customer_name': CUST.customer_name,
            'role_id': 6,
            'is_cc_customer': False,
            'is_monitoring_user': True,
            'is_superuser': False,
            'is_account_admin': False,
            'is_enterprise_admin': False
        })
        session = self._engine.SessionStore()
        session.save()
        self._session = session
        self.client.cookies[settings.SESSION_COOKIE_NAME] = self._session.session_key
        self._session['user'] = self._user
        self._session.save()

    def tearDown(self):
        settings.SESSION_ENGINE = self._original_session_engine
        self._session.delete()

    def test_view(self):
        url = '/rules/occurrences/'
        resp = self.client.get(url)
