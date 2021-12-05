
from jolt import Task
from jolt.error import raise_task_error_if


class CMake(Task):
    """ Builds and publishes a CMake project """

    abstract = True

    cmakelists = "CMakeLists.txt"
    """ Path to CMakeLists.txt or directory containing CMakelists.txt """

    options = []
    """ List of options and their values (``option[:type]=value``) """

    def run(self, deps, tools):
        raise_task_error_if(not self.cmakelists, self, "cmakelists attribute has not been defined")

        cmake = tools.cmake()
        cmake.configure(tools.expand(self.cmakelists), *["-D" + tools.expand(option) for option in self.options])
        cmake.build()
        cmake.install()

    def publish(self, artifact, tools):
        cmake = tools.cmake()
        cmake.publish(artifact)
