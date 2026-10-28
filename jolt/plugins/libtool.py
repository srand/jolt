from jolt import attributes, filesystem as fs, Task


class Libtool(object):
    def __init__(self, tools):
        self.tools = tools

    def relocate(self, artifact, dirs=None, prefix=None, path=None):
        """
        Replaces a path in libtool archive files (.la). Returns True if any
        files were found.

        Files are searched for in the listed directories of the artifact, or
        in the whole artifact if no directories are listed.

        Args:
            prefix (str): Path to replace. Default: the install prefix of the artifact.
            path (str): Replacement path. Default: the final path of the artifact.
        """
        prefix = str(artifact.strings.install_prefix) if prefix is None else prefix
        path = artifact.final_path if path is None else path
        found = False
        for dir in dirs or ["."]:
            pattern = "*.la" if dirs else "**/*.la"
            with self.tools.cwd(artifact.path, dir):
                for file in self.tools.glob(pattern):
                    self.tools.replace_in_file(file, prefix, path)
                    found = True
        return found

    def publish(self, artifact, dirs=None):
        """
        Replaces the install prefix in libtool archive files (.la) with the
        path of the artifact, and records the path for unpack().
        """
        if self.relocate(artifact, dirs):
            artifact.strings.libtool_prefix = artifact.final_path

    def unpack(self, artifact, dirs=None):
        """
        Relocates libtool archive files (.la) of an artifact that has moved
        to another cache.

        The files refer to the artifact and to the artifacts of its
        requirements in the cache where it was published. Since artifacts
        are found in the same place in every cache, the location of the old
        cache is replaced with the location of the new one.
        """
        prefix = artifact.strings.libtool_prefix
        if prefix is None or str(prefix) == artifact.final_path:
            return
        old_cache = fs.path.dirname(fs.path.dirname(str(prefix)))
        new_cache = fs.path.dirname(fs.path.dirname(artifact.final_path))
        self.relocate(artifact, dirs, prefix=old_cache, path=new_cache)
        artifact.strings.libtool_prefix = artifact.final_path


def relocate(dirs=["lib"]):
    """
    Relocate libtool archive files (.la) published by task.

    When an artifact is published, all .la files found in the specified
    directories will have their install prefix updated to the artifact's final path.
    The path is stored in the artifact's strings metadata under the key
    'libtool_prefix', so that the files can be relocated again when the
    artifact is unpacked in another cache.

    Autotools tasks only publish .la files if their ``libtool`` attribute is set.

      :param dirs: List of directories inside the artifact to relocate .la files in.

    """

    def decorate(cls):
        original_publish = cls.publish
        original_unpack = cls.unpack

        def publish(self, artifact, tools):
            original_publish(self, artifact, tools)
            Libtool(tools).publish(artifact, dirs)

        def unpack(self, artifact, tools):
            if original_unpack is not Task.unpack:
                original_unpack(self, artifact, tools)
            Libtool(tools).unpack(artifact, dirs)

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
