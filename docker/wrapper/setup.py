from setuptools import setup, find_packages
from codecs import open
from os import path

here = path.abspath(path.dirname(__file__))
name = "jolt_docker"
exec(open('jolt_docker/version.py').read())


# Get the long description from the README file
with open(path.join(here, 'README.rst'), encoding='utf-8') as f:
    long_description = f.read()

setup(
    name=name,
    version=__version__,
    description='A task executor',
    long_description=long_description,
    url='https://bitbucket.org/rand_r/jolt',
    author='Robert Andersson',
    author_email='rand_r@bitbucket.org',
    classifiers=[
        'Development Status :: 4 - Beta',
        'Intended Audience :: Developers',
        'Topic :: Software Development :: Build Tools',
        'License :: OSI Approved :: GNU General Public License v2 (GPLv2)',
        'Programming Language :: Python :: 3',
    ],
    keywords='build msbuild xcode make pam bazel jolt conan',
    packages=find_packages(exclude=['contrib', 'docs', 'tests']),
    install_requires=[],
    dependency_links=[],
    entry_points={
        'console_scripts': [
            'jolt=jolt_docker.__main__:main',
        ],
    },
)
