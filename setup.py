import os
import sys
from distutils.core import setup


def fullsplit(path, result=None):
    """
    Split a pathname into components (the opposite of os.path.join) in a
    platform-neutral way.
    """
    if result is None:
        result = []
    head, tail = os.path.split(path)
    if head == '':
        return [tail] + result
    if head == path:
        return result
    return fullsplit(head, [tail] + result)


packages, data_files = [], []
root = os.path.dirname(__file__)
package_root = os.path.join(root, 'rules')
for dirpath, dirnames, filenames in os.walk(package_root):
    # Ignore dirnames that start with '.'
    for i, dirname in enumerate(dirnames):
        if dirname.startswith('.'): del dirnames[i]
    if '__init__.py' in filenames:
        packages.append('.'.join(fullsplit(dirpath[len(root):])))
    elif filenames:
        data_files.append((dirpath, [os.path.join(dirpath, f) for f in filenames]))

sys.path.insert(0, root)
version = __import__('rules').get_version()
del sys.path[0]

#TODO implement download_url based on version
download_url = 'http://packages.corp.verisys.com/rule-reactor-{}.tar.gz'.format(version)

setup(
    name='rules',
    version=version,
    download_url=download_url,
    description='Reusable app for defining business rules.',
    author='Verisys',
    author_email='alldev@verisys.com',
    url='www.verisys.com',
    packages=packages,
    data_files=data_files,
    # TODO how do we specify where to get mablibs?
    install_requires=('django>=1.4.6', 'madlibs')
)
