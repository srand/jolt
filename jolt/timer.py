from threading import Thread, Event


class Timer(Thread):
    def __init__(self, interval, function, args=None, kwargs=None):
        Thread.__init__(self)
        self.interval = interval
        self.function = function
        self.args = args if args is not None else []
        self.kwargs = kwargs if kwargs is not None else {}
        self.finished = Event()

    def cancel(self):
        self.finished.set()

    def run(self):
        while True:
            self.finished.wait(self.interval)
            if not self.finished.is_set():
                self.function(*self.args, **self.kwargs)
            else:
                break
