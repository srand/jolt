from setuptools import setup, find_packages
from setuptools.command.build_py import build_py
from codecs import open
from os import makedirs, path
from shutil import copyfile

here = path.abspath(path.dirname(__file__))
name = "jolt"
exec(open("jolt/version.py").read())


# Get the long description from the README file
with open(path.join(here, "README.rst"), encoding="utf-8") as f:
    long_description = f.read()

try:
    with open(path.join(here, "requirements.txt"), encoding="utf-8") as f:
        pinned_reqs = f.readlines()
except FileNotFoundError:
    pinned_reqs = []


class BuildCommand(build_py):
    def run(self):
        build_py.run(self)

        # Install additional files required by selfdeploy plugin
        if not self.dry_run:
            target_dir = path.join(self.build_lib, name, "plugins", "selfdeploy")
            makedirs(target_dir, exist_ok=True)
            for fn in ["setup.py", "README.rst"]:
                copyfile(path.join(here, fn), path.join(target_dir,fn))

setup(
    name=name,
    cmdclass={"build_py": BuildCommand},
    version=__version__,
    python_requires=">=3.8",
    description="A task executor",
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
    packages=find_packages(exclude=["contrib", "docs", "tests"]),
    install_requires=pinned_reqs or [
        "bz2file",
        "click>=8.1",
        "colorama",
        "fasteners",
        "grpcio>=1.62.2",
        "jinja2",
        "keyring",
        "keyrings.alt",
        "importlib_metadata",
        "lxml",
        "multi_key_dict",
        "ninja",
        "protobuf",
        "psutil",
        "pygit2",
        "requests",
        "zstandard",
        "tqdm",
    ],
    dependency_links=[],
    extras_require={
        "allure": ["allure-python-commons"],
        "conan": ["conan<2.0"],
        "dev": ["check-manifest"],
        "doc": ["sphinx-click", "sphinx-rtd-theme"],
        "test": ["coverage"],
    },
    package_data={
        "jolt": ["**/*.sh", "**/*.xslt", "**/*.template", "**/fstree-*-x86_64"],
    },
    entry_points={
        "console_scripts": [
            "jolt=jolt.__main__:main",
        ],
    },
)
