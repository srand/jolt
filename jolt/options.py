
class JoltOptions(object):
    """ Jolt options that control the behavior of builds. """

    debug = False
    """ Enable debug mode. Break into debugger on exceptions. """

    download = True
    """ Enable downloading of remote artifacts, both session and persistent. """

    download_session = True
    """ Enable downloading of remote session artifacts. """

    keep_going = False
    """ Keep going with the build after a task fails. """

    local = False
    """ Disable network access. """

    network = False
    """ Distribute tasks to workers. """

    upload = True
    """ Enable uploading of artifacts. """

    worker = False
    """ Running as a worker. """

    salt = None
    """ Salt for hashing (--salt). """

    jobs = 1
    """ Number of concurrent local tasks to run (1). """

    mute = False
    """ Mute task output, until a task fails. """

    def __init__(self, **kwargs):
        self.__dict__.update(kwargs)
