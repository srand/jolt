Installation instructions for virtualenv
==============================================

0. pip install virtualenv
1. virtualenv joltdev
2. . joltdev/bin/activate
3. pip install -e .


Running
==============================================

1. jolt list
2. jolt info example
3. jolt build example

# With Artifactory and Jenkins on localhost
4. jolt -c example.conf build -n example  

Tasks are defined in example.jolt.
