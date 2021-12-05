from jolt import influence
from jolt.plugins import ninja, yamltask


@influence.attribute("yaml")
class LibraryYamlTask(ninja.CXXLibrary):
    def run(self, d, t):
        super(ninja.CXXLibrary, self).run(d, t)
        yamltask.YamlTask.run(self, d, t)

    def publish(self, a, t):
        super(ninja.CXXLibrary, self).publish(a, t)
        yamltask.YamlTask.publish(self, a, t)


@yamltask.register
class LibraryYamlTaskBuilder(yamltask.YamlTaskBuilder):
    name = "library"

    def build(self, ytask):
        class LoadedYamlTask(LibraryYamlTask):
            # From Task
            name = None
            requires = []
            cacheable = True
            commands = []
            collects = []
            extends = ""
            fast = False
            influence = []
            joltdir = "."
            joltproject = None
            metadata = {}
            selfsustained = False
            taint = False
            weight = False

            # From CXXLibrary
            asflags = []
            cflags = []
            cxxflags = []
            depimports = []
            incpaths = []
            libpaths = []
            libraries = []
            ldflags = []
            macros = []
            sources = []
            publishdir = "lib/"
            shared = False
            source_influence = True
            binary = None
            incremental = True

        for key, obj in ytask.items():
            setattr(LoadedYamlTask, key, obj)

        LoadedYamlTask.yaml = ytask

        return LoadedYamlTask


@influence.attribute("yaml")
class ExecutableYamlTask(ninja.CXXExecutable):
    def run(self, d, t):
        super(ninja.CXXExecutable, self).run(d, t)
        yamltask.YamlTask.run(self, d, t)

    def publish(self, a, t):
        super(ninja.CXXExecutable, self).publish(a, t)
        yamltask.YamlTask.publish(self, a, t)


@yamltask.register
class ExecutableYamlTaskBuilder(yamltask.YamlTaskBuilder):
    name = "executable"

    def build(self, ytask):
        class LoadedYamlTask(ExecutableYamlTask):
            # From Task
            name = None
            requires = []
            cacheable = True
            commands = []
            collects = []
            extends = ""
            fast = False
            influence = []
            joltdir = "."
            joltproject = None
            metadata = {}
            selfsustained = False
            taint = False
            weight = False

            # From CXXExecutable
            asflags = []
            cflags = []
            cxxflags = []
            depimports = []
            incpaths = []
            libpaths = []
            libraries = []
            ldflags = []
            macros = []
            sources = []
            publishdir = "lib/"
            shared = False
            source_influence = True
            binary = None
            incremental = True

        for key, obj in ytask.items():
            setattr(LoadedYamlTask, key, obj)

        LoadedYamlTask.yaml = ytask

        return LoadedYamlTask
