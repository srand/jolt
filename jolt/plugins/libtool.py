from jolt import attributes


class Libtool(object):
    def __init__(self, tools):
        self.tools = tools

    def relocate(self, artifact, dirs=["lib"], prefix=None):
        prefix = str(artifact.strings.install_prefix) if prefix is None else prefix
        for dir in dirs:
            with self.tools.cwd(artifact.path, dir):
                for file in self.tools.glob("*.la"):
                    self.tools.replace_in_file(file, prefix, artifact.final_path)



def relocate(dirs=["lib"]):
    """
    Relocate libtool archive files (.la) published by task.

    When an artifact is published, all .la files found in the specified
    directories will have their install prefix updated to the artifact's final path.
    The original install prefix is stored in the artifact's strings metadata
    under the key 'libtool_prefix' for use during unpacking.

      :param dirs: List of directories inside the artifact to relocate .la files in.
      
    """

    def decorate(cls):
        original_publish = cls.publish
        original_unpack = cls.unpack

        def publish(self, artifact, tools):
            original_publish(self, artifact, tools)
            lt = Libtool(tools)
            lt.relocate(artifact, dirs, prefix=artifact.strings.install_prefix)
            artifact.libtool_prefix = artifact.final_path

        def unpack(self, artifact, tools):
            original_unpack(self, artifact, tools)
            lt = Libtool(tools)
            lt.relocate(artifact, dirs, prefix=artifact.strings.libtool_prefix)
            artifact.strings.libtool_prefix = None

        cls.publish = publish
        cls.unpack = unpack

        return cls

    return decorate



def requires():
    """ Decorator to add Libtool requirement to a task. """

    import jolt.pkgs.libtool

    def decorate(cls):
        cls = attributes.requires("requires_libtool")(cls)
        cls.requires_libtool = ["libtool"]
        return cls

    return decorate