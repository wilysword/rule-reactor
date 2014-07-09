from django.conf import settings

if not hasattr(settings, 'RULES_OWNER_MODEL'):
    settings.RULES_OWNER_MODEL = 'auth.user'

if not hasattr(settings, 'RULES_CONCRETE_MODELS'):
    settings.RULES_CONCRETE_MODELS = True
