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
    import discover_runner
except ImportError:
    pass
else:
    TEST_RUNNER = 'discover_runner.DiscoverRunner'
