from setuptools import setup, find_packages
from codecs import open
from os import path

here = path.abspath(path.dirname(__file__))

# Get the long description from the README file
with open(path.join(here, 'README.rst'), encoding='utf-8') as f:
    long_description = f.read()

setup(
    name='jolt',
    version='0.9.12',
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
    install_requires=["requests", "click>=7.0", "networkx", "keyring", "keyrings.alt",
                      "jinja2", "python-jenkins", "multi_key_dict",
                      "tqdm<=4.29.1", "bz2file", "colorama", "ninja-syntax",
                      "pyyaml", "fasteners", "ntfsutils", "pygit2", "lxml"],
    dependency_links=[],
    extras_require={
        'allure': ['allure-python-commons'],
        'amqp': ['pika'],
        'dev': ['check-manifest'],
        'test': ['coverage'],
    },
    package_data={
        'jolt': ['**/*.xslt'],
    },
    entry_points={
        'console_scripts': [
            'jolt=jolt.__main__:main',
        ],
    },
)
