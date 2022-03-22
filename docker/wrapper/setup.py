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
    url="https://github.com/srand/jolt",
    author="Robert Andersson",
    author_email="srand@github.com",
    classifiers=[
        "Development Status :: 5 - Production/Stable",
        "Intended Audience :: Developers",
        "Intended Audience :: System Administrators",
        "Topic :: Software Development :: Build Tools",
        "Topic :: Software Development :: Testing",
        "License :: OSI Approved :: GNU General Public License v2 (GPLv2)",
        "Operating System :: MacOS :: MacOS X",
        "Operating System :: Microsoft :: Windows",
        "Operating System :: POSIX",
        "Programming Language :: C",
        "Programming Language :: C++",
        "Programming Language :: Java",
        "Programming Language :: JavaScript",
        "Programming Language :: Python :: 3",
    ],
    keywords=[
        "bazel",
        "build",
        "cmake",
        "conan",
        "jolt",
        "make",
        "meson",
        "msbuild",
        "xcode",
    ],
    packages=find_packages(exclude=['contrib', 'docs', 'tests']),
    install_requires=[],
    dependency_links=[],
    entry_points={
        'console_scripts': [
            'jolt=jolt_docker.__main__:main',
        ],
    },
)
