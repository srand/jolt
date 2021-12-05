
class JoltOptions(object):
    def __init__(self, **kwargs):
        self.debug = False
        self.default = []
        self.download = True
        self.keep_going = False
        self.local = False
        self.network = False
        self.upload = True
        self.worker = False
        self.salt = None
        self.jobs = 1
        self.__dict__.update(kwargs)
