import os
from setuptools import setup, find_packages


def read(fname):
    return open(os.path.join(os.path.dirname(__file__), fname)).read()


setup(
    name = 'ziu',
    version = '0.1.0',
    author = 'Kris',
    author_email = '31852063+krisfris@users.noreply.github.com',
    description = ('ziu file manager'),
    license = 'MIT',
    keywords = '',
    url = 'https://github.com/krisfris/ziu',
    packages=find_packages(exclude=['docs', 'tests']),
    package_data={'ziu': ['pics/*', 'qss/*', 'designer/*']},
    long_description=read('README.md'),
    long_description_content_type='text/markdown',
    data_files=[('', ['LICENSE', 'README.md'])],
    install_requires=['pyqt5', 'send2trash'],
    entry_points = {
       'console_scripts': [
            'ziu = ziu.main:run'
        ]
    }
)

