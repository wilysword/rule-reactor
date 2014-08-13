from django.conf import settings

if not hasattr(settings, 'RULES_OWNER_MODEL'):
    settings.RULES_OWNER_MODEL = None

if not hasattr(settings, 'RULES_CONCRETE_MODELS'):
    settings.RULES_CONCRETE_MODELS = True

if not hasattr(settings, 'RULES_MODULES'):
    settings.RULES_MODULES = ()
