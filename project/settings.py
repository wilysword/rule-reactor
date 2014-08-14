import os
BASE_DIR = os.path.dirname(os.path.dirname(__file__))
DEBUG = True

SECRET_KEY = 'Not really a secret key, here for docs and testing.'

INSTALLED_APPS = ('django.contrib.auth', 'django.contrib.contenttypes', 'rules')

RULES_OWNER_MODEL = 'auth.User'

SPHINX = {'exclude_patterns': ('setup.py',)}

DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': ':memory:',
    },
}

try:
    import django_nose
except ImportError:
    pass
else:
    TEST_RUNNER = 'django_nose.NoseTestSuiteRunner'
    NOSE_ARGS = ('rules', '--with-coverage', '--cover-erase', '--cover-package=rules')
    INSTALLED_APPS += ('django_nose',)
