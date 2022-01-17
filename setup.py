from setuptools import setup, find_packages
from setuptools.command.build_py import build_py
from codecs import open
from os import makedirs, path
from shutil import copyfile

here = path.abspath(path.dirname(__file__))
name = "jolt"
exec(open('jolt/version.py').read())


# Get the long description from the README file
with open(path.join(here, 'README.rst'), encoding='utf-8') as f:
    long_description = f.read()


class BuildCommand(build_py):
    def run(self):
        build_py.run(self)

        # Install additional files required by selfdeploy plugin
        if not self.dry_run:
            target_dir = path.join(self.build_lib, name, "plugins", "selfdeploy")
            makedirs(target_dir)
            for fn in ["setup.py", "README.rst"]:
                copyfile(path.join(here, fn), path.join(target_dir,fn))

setup(
    name=name,
    cmdclass={"build_py": BuildCommand},
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
    install_requires=[
        "bz2file",
        "click>=7.0",
        "colorama",
        "fasteners",
        "jinja2",
        "keyring",
        "keyrings.alt",
        "lxml",
        "multi_key_dict",
        "ninja-syntax",
        "pygit2",
        "requests",
        "tqdm",
    ],
    dependency_links=[],
    extras_require={
        'allure': ['allure-python-commons'],
        'amqp': ['pika'],
        'dev': ['check-manifest'],
        'doc': ['sphinx-click', 'sphinx-rtd-theme'],
        'test': ['coverage'],
    },
    package_data={
        'jolt': ['**/*.sh', '**/*.xslt', '**/*.template'],
    },
    entry_points={
        'console_scripts': [
            'jolt=jolt.__main__:main',
        ],
    },
)
