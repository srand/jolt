from datetime import datetime, timedelta

from jolt import utils


class ArtifactEvictionStrategy(object):
    name = None

    def __init__(self, *args, **kwargs):
        pass

    def is_evictable(self, artifact):
        """ Return True if eviction is permissible. """
        return True

    @property
    def value(self):
        return self.name


class Immediately(ArtifactEvictionStrategy):
    name = "immediately"

    def is_evictable(self, artifact):
        return True


class Never(ArtifactEvictionStrategy):
    name = "never"

    def is_evictable(self, artifact):
        return False


class After(ArtifactEvictionStrategy):
    name = "after"

    def __init__(self, *args, **kwargs):
        self.delta = timedelta(*args, **kwargs)

    def is_evictable(self, artifact):
        return datetime.now() - artifact["created"] > self.delta

    @property
    def value(self):
        return {
            self.name: {
                "days": self.delta.days,
                "seconds": self.delta.seconds
            }
        }


class WhenUnusedFor(ArtifactEvictionStrategy):
    name = "when_unused_for"

    def __init__(self, *args, **kwargs):
        self.delta = timedelta(*args, **kwargs)

    def is_evictable(self, artifact):
        return datetime.now() - artifact["used"] > self.delta

    @property
    def value(self):
        return {
            self.name: {
                "days": self.delta.days,
                "seconds": self.delta.seconds
            }
        }


@utils.Singleton
class ArtifactEvictionStrategyRegister(object):
    def __init__(self):
        self.strategies = {}

    def add(self, strategy):
        self.strategies[strategy.name] = strategy

    def find(self, expiration_data):
        if type(expiration_data) is str:
            return self.strategies.get(expiration_data, Immediately)()
        if type(expiration_data) is dict:
            for strategy, data in expiration_data.items():
                strategy = self.strategies.get(strategy)
                return strategy(**data) if strategy else Immediately()
        return Immediately()


ArtifactEvictionStrategyRegister.get().add(Immediately)
ArtifactEvictionStrategyRegister.get().add(Never)
ArtifactEvictionStrategyRegister.get().add(After)
ArtifactEvictionStrategyRegister.get().add(WhenUnusedFor)
