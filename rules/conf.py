from django.conf import settings

if not hasattr(settings, 'RULES_OWNER_MODEL'):  # pragma: no cover
    settings.RULES_OWNER_MODEL = None

if not hasattr(settings, 'RULES_CONCRETE_MODELS'):  # pragma: no cover
    settings.RULES_CONCRETE_MODELS = True

if not hasattr(settings, 'RULES_MODULES'):  # pragma: no cover
    settings.RULES_MODULES = ()
