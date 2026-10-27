import contextlib
from datetime import datetime
import sqlite3
import statistics

from jolt import common_pb2 as common_pb
from jolt import config
from jolt import filesystem as fs
from jolt import log
from jolt.hooks import TaskHook, TaskHookFactory


log.verbose("[AutoWeight] Loaded")


class WeightHooks(TaskHook):
    def __init__(self):
        self._samples = config.getint("autoweight", "samples", 10)
        self._db_path = fs.path.join(config.get_cachedir(), "autoweight.db")
        with self._db() as db:
            self._db_create_tables(db)
            samples = self._db_select_samples(db)
        # Median is robust against occasional outliers, e.g. cold cache builds
        self._weights = {name: statistics.median(d) for name, d in samples.items()}

    @contextlib.contextmanager
    def _db(self):
        db = sqlite3.connect(self._db_path)
        try:
            db.execute("PRAGMA busy_timeout = 5000")
            db.execute("PRAGMA journal_mode = WAL")
            yield db
        finally:
            db.close()

    def _db_create_tables(self, db):
        cur = db.cursor()

        # Execution time samples for each task
        cur.execute("CREATE TABLE IF NOT EXISTS samples "
                    "(name text, duration integer, finished timestamp)")
        cur.execute("CREATE INDEX IF NOT EXISTS samples_name ON samples (name, finished)")
        db.commit()

    def _db_insert_sample(self, db, name, duration):
        cur = db.cursor()
        cur.execute("INSERT INTO samples VALUES (?,?,?)", (name, duration, datetime.now().isoformat(" ")))

        # Evict samples in FIFO order, committed together with the insert
        cur.execute("DELETE FROM samples WHERE name = ? AND rowid NOT IN "
                    "(SELECT rowid FROM samples WHERE name = ? ORDER BY finished DESC LIMIT ?)",
                    (name, name, self._samples))
        db.commit()

    def _db_select_samples(self, db):
        cur = db.cursor()
        samples = {}
        for name, duration in cur.execute(
                "SELECT name, duration FROM "
                "(SELECT name, duration, ROW_NUMBER() OVER "
                "(PARTITION BY name ORDER BY finished DESC) AS n FROM samples) "
                "WHERE n <= ?", (self._samples,)):
            samples.setdefault(name, []).append(duration)
        return samples

    def task_created(self, task):
        weight = self._weights.get(task.qualified_name)
        if weight is not None:
            task.weight = weight

    def task_finished(self, task):
        # Only sample executions, not downloads or uploads
        if task.status() != common_pb.TaskStatus.TASK_PASSED:
            return
        with self._db() as db:
            self._db_insert_sample(db, task.qualified_name, task.duration_running.seconds)


@TaskHookFactory.register
class WeightFactory(TaskHookFactory):
    def create(self, env):
        return WeightHooks()
