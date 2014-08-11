__all__ = ('VERSION', 'get_version')
VERSION = (0, 1, 0, 'dev')


def get_version():
    return '.'.join(str(i) for i in VERSION)


def discover(force=False):
    global _DISCOVERED
    if _DISCOVERED and not force:
        return
    from .conf import settings
    modules = {app + '.rules' for app in settings.INSTALLED_APPS}
    modules.update(settings.RULES_MODULES)
    for module in modules:
        try:
            __import__(module)
        except ImportError:
            pass
    _DISCOVERED = True

_DISCOVERED = False
