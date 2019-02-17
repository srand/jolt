


class JoltOptions(object):
    def __init__(self, **kwargs):
        self.network = False
        self.local = False
        self.download = True
        self.upload = True
        self.keep_going = False
        self.worker = False
        self.default = []
        self.__dict__.update(kwargs)
