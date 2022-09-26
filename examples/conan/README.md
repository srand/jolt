# Mini guide to Conan
Just setting the correct packages 

Example:
class FetchGTest(Conan):
    packages = ["gtest/cci.20210126"]

usually works right out of the box. 

If you get build issues then you might need to supply more parameters to conan.
This is made through the settings, options, generators and more. See
https://jolt.readthedocs.io/en/latest/reference.html#conan for more info.

#### Setting libstdc++ version

It is important to set the compiler.libcxx correctly. 
This can be set to either libstdc++ or libstdc++11.
If you get undefined references during the build then change this.

Example:
settings = ["compiler.libcxx=libstdc++11"]


#### Getting package info
These settings are from the gtest package on conan.io
By selecting a package by os, arch, and compiler you can 
get the necessary setting for your build.


#### Example configuration
This configuration is an example of how a linux, x86_64 and gcc
configuration could look like.

Example:
[settings]
    arch=x86_64
    build_type=Release
    compiler=gcc
    compiler.libcxx=libstdc++11
    compiler.version=11
    os=Linux

[requires]


[options]
    build_gmock=True
    fPIC=True
    hide_symbols=False
    shared=False

[full_settings]
    arch=x86_64
    build_type=Release
    compiler=gcc
    compiler.libcxx=libstdc++11
    compiler.version=11
    os=Linux

[full_requires]


[full_options]
    build_gmock=True
    fPIC=True
    hide_symbols=False
    no_main=False
    shared=False

[recipe_hash]
    dafbdf84b58cd687075ace7314651c1a

[env]
