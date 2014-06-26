__all__ = ('VERSION', 'get_version')
VERSION = (0, 1, 'dev')


def get_version():
    return '.'.join(str(i) for i in VERSION)
