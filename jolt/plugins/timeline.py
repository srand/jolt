import os
import socket
import time

from jolt import common_pb2 as common_pb
from jolt import log
from jolt import tools
from jolt import utils
from jolt.hooks import TaskHook, TaskHookFactory
from jolt import config


NAME_LOG = "Timeline"

# Geometry of the rendered SVG chart, in user units
CHART_WIDTH = 1200
LABEL_WIDTH = 50
AXIS_HEIGHT = 30
MARGIN = 20
GAP_WIDTH = 24

# Row geometry (row height, bar height, font size), normal and compact
ROW_NORMAL = (22, 16, 11)
ROW_COMPACT = (14, 11, 9)
COMPACT_ROWS = 40

# Idle periods longer than this, both in seconds and as a fraction
# of the total duration, are collapsed into a break on the time axis.
GAP_MIN_SECONDS = 60
GAP_MIN_FRACTION = 0.1

# Bars narrower than this are drawn without a label
LABEL_MIN_WIDTH = 40

# Candidate axis tick intervals, in seconds
TICK_STEPS = [1, 2, 5, 10, 15, 30, 60, 120, 300, 600, 900, 1800, 3600, 7200, 10800, 21600]


def format_duration(seconds):
    seconds = int(seconds)
    hours, seconds = divmod(seconds, 3600)
    minutes, seconds = divmod(seconds, 60)
    text = ""
    if hours > 0:
        text += f"{hours}h "
    if minutes > 0:
        text += f"{minutes}min "
    return text + f"{seconds}s"


def common_prefix(names, sep="/"):
    """ Longest prefix shared by all names, ending with a separator. """
    if len(names) < 2:
        return ""
    prefix = os.path.commonprefix(list(names))
    return prefix[:prefix.rfind(sep) + 1]


class TimelineHooks(TaskHook):
    def __init__(self):
        self.path = os.path.join(
            config.get_workdir(),
            config.get("timeline", "path", "timeline.html")
        )
        self.start = time.time()
        self.entries = []
        self.running = {}
        self.tools = tools.Tools()

    def started(self, task, kind):
        self.running[task] = {
            "task": task,
            "deps": list(task.descendants),
            "name": task.short_qualified_name,
            "kind": kind,
            "start": time.time(),
        }

    def finished(self, task, status):
        entry = self.running.pop(task, None)
        if entry is None:
            return
        entry["end"] = time.time()
        entry["status"] = status
        entry["worker"] = getattr(task, "worker", None) or socket.gethostname()
        self.entries.append(entry)
        self.render()

    def segments(self, end):
        """
        Splits the time from start to end into busy segments and
        long idle gaps, as a list of (start, end, is_gap) tuples.
        """
        span = end - self.start
        threshold = max(GAP_MIN_SECONDS, span * GAP_MIN_FRACTION)

        segments = []
        busy_start = busy_end = self.start
        for entry in sorted(self.entries, key=lambda e: e["start"]):
            if entry["start"] - busy_end > threshold:
                segments.append((busy_start, busy_end, False))
                segments.append((busy_end, entry["start"], True))
                busy_start = entry["start"]
            busy_end = max(busy_end, entry["end"])
        segments.append((busy_start, end, False))
        return segments

    def critical_path(self):
        """
        Walks backwards from the last finished entry, each time stepping
        to the dependency, or earlier step of the same task, that finished
        last. Returns the entries on the path in chronological order.
        """
        by_task = {}
        for entry in self.entries:
            if entry.get("task") is not None:
                by_task.setdefault(entry["task"], []).append(entry)

        path = []
        entry = max(self.entries, key=lambda e: e["end"], default=None)
        while entry is not None and entry.get("task") is not None:
            path.append(entry)
            candidates = list(by_task[entry["task"]])
            for dep in entry["deps"]:
                candidates.extend(by_task.get(dep, []))
            candidates = [
                e for e in candidates
                if e["end"] <= entry["start"] or (e["task"] is not entry["task"] and e["end"] <= entry["end"])
            ]
            entry = max(candidates, key=lambda e: e["end"], default=None)
        return list(reversed(path))

    def layout(self):
        end = max([e["end"] for e in self.entries] + [self.start + 1])
        segments = self.segments(end)
        gaps = [s for s in segments if s[2]]
        busy = max(sum(s[1] - s[0] for s in segments if not s[2]), 0.001)
        scale = (CHART_WIDTH - LABEL_WIDTH - MARGIN - len(gaps) * GAP_WIDTH) / busy

        # Pixel offset of each segment
        offsets = []
        pos = LABEL_WIDTH
        for start, stop, gap in segments:
            offsets.append(pos)
            pos += GAP_WIDTH if gap else (stop - start) * scale

        def x(t):
            for (start, stop, gap), offset in zip(segments, offsets):
                if t <= stop:
                    if gap:
                        return offset + (t - start) / (stop - start) * GAP_WIDTH
                    return offset + (t - start) * scale
            return pos

        # Assign each entry to the first free lane of its worker
        # so that concurrent tasks never overlap.
        workers = {}
        for entry in sorted(self.entries, key=lambda e: e["start"]):
            lanes = workers.setdefault(entry["worker"], [])
            for lane, lane_end in enumerate(lanes):
                if lane_end <= entry["start"]:
                    break
            else:
                lane = len(lanes)
                lanes.append(None)
            lanes[lane] = entry["end"]
            entry["lane"] = lane

        total_rows = sum(len(lanes) for lanes in workers.values())
        row_height, bar_height, font_size = \
            ROW_COMPACT if total_rows > COMPACT_ROWS else ROW_NORMAL
        prefix = common_prefix([e["name"] for e in self.entries])

        critical = self.critical_path()
        critical_ids = set(id(e) for e in critical)

        rows = 0
        groups = []
        bars = []
        # Workers are numbered in order of their first task
        for number, worker in enumerate(workers, start=1):
            groups.append({
                "name": worker,
                "number": number,
                "y": AXIS_HEIGHT + rows * row_height,
                "height": len(workers[worker]) * row_height,
            })
            for entry in self.entries:
                if entry["worker"] != worker:
                    continue
                width = max(x(entry["end"]) - x(entry["start"]), 1)
                bars.append({
                    "name": entry["name"],
                    "label": entry["name"][len(prefix):] if width >= LABEL_MIN_WIDTH else "",
                    "kind": entry["kind"],
                    "status": entry["status"],
                    "x": x(entry["start"]),
                    "y": AXIS_HEIGHT + (rows + entry["lane"]) * row_height + (row_height - bar_height) / 2,
                    "width": width,
                    "duration": format_duration(entry["end"] - entry["start"]),
                    "critical": id(entry) in critical_ids,
                })
            rows += len(workers[worker])

        step = next((s for s in TICK_STEPS if busy / s <= 12), TICK_STEPS[-1])
        ticks = [
            {"x": x(self.start + t), "label": format_duration(t).replace(" 0s", "")}
            for t in range(0, int(end - self.start) + 1, step)
            if any(not gap and start <= self.start + t <= stop for start, stop, gap in segments)
        ]

        return {
            "width": CHART_WIDTH,
            "height": AXIS_HEIGHT + rows * row_height + MARGIN,
            "label_width": LABEL_WIDTH,
            "row_height": row_height,
            "bar_height": bar_height,
            "font_size": font_size,
            "prefix": prefix,
            "groups": groups,
            "bars": bars,
            "critical": bool(critical),
            "critical_duration": format_duration(
                sum(e["end"] - e["start"] for e in critical)),
            "ticks": ticks,
            "gaps": [
                {"x": x(start), "width": GAP_WIDTH, "duration": format_duration(stop - start)}
                for start, stop, _ in gaps
            ],
            "duration": format_duration(end - self.start),
        }

    def render(self):
        failed = [e for e in self.entries if e["status"] in ("failed", "unstable")]
        completed = [e for e in self.entries if e["status"] != "cancelled"]
        timeline = utils.render(
            "timeline.html.template",
            chart=self.layout(),
            completed=len(completed),
            failed=len(failed),
            passed=not any(e["status"] == "failed" for e in failed))

        self.tools.write_file(self.path, timeline, expand=False)

    def task_started_download(self, task):
        self.started(task, "download")

    def task_started_execution(self, task):
        self.started(task, "execution")

    def task_started_upload(self, task):
        self.started(task, "upload")

    def task_finished_download(self, task):
        self.finished(task, "passed")

    def task_finished_upload(self, task):
        self.finished(task, "passed")

    def task_finished_execution(self, task):
        self.finished(task, "passed")

    def task_failed(self, task):
        if task.status() == common_pb.TaskStatus.TASK_CANCELLED:
            self.finished(task, "cancelled")
        else:
            self.finished(task, "failed")

    def task_unstable(self, task):
        self.finished(task, "unstable")


@TaskHookFactory.register
class TimelineFactory(TaskHookFactory):
    def create(self, env):
        log.verbose(NAME_LOG + " Loaded")
        return TimelineHooks()
