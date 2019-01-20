


class JoltOptions(object):
    def __init__(self, **kwargs):
        self.network = False
        self.download = True
        self.upload = True
        self.__dict__.update(kwargs)
