"""Background jobs with bounded memory.

Only the last MAX_LINES lines of a job's output are kept in memory. The complete
output is streamed to a file on disk (and saved with the release). Browsers ask
for "lines since N" so each poll transfers only what is new. Finished jobs are
pruned, keeping the most recent few.
"""
import collections
import os
import threading
import time
import uuid

from . import library as lib

MAX_LINES = 4000
KEEP_FINISHED = 8
LINE_CAP = 2000  # characters per line

_jobs = collections.OrderedDict()
_lock = threading.Lock()


class Job:
    def __init__(self, project, label=""):
        self.id = uuid.uuid4().hex[:10]
        self.project = project
        self.label = label
        self.lines = collections.deque(maxlen=MAX_LINES)
        self.total = 0
        self.done = False
        self.results = []
        self.started = time.time()
        d = os.path.join(lib.DATA, "joblogs")
        os.makedirs(d, exist_ok=True)
        self.path = os.path.join(d, self.id + ".log")
        self._fh = open(self.path, "w", encoding="utf-8", errors="replace")
        self._lk = threading.Lock()

    def log(self, line):
        line = str(line)
        if len(line) > LINE_CAP:
            line = line[:LINE_CAP] + " ...[line cut]"
        with self._lk:
            self.lines.append(line)
            self.total += 1
            if self._fh:
                self._fh.write(line + "\n")
                self._fh.flush()

    def finish(self):
        with self._lk:
            self.done = True
            if self._fh:
                self._fh.close()
                self._fh = None

    def full_log(self):
        try:
            with open(self.path, encoding="utf-8", errors="replace") as f:
                return f.read()
        except OSError:
            return "\n".join(self.lines)

    def snapshot(self, since=0):
        with self._lk:
            base = self.total - len(self.lines)  # index of the first line still in memory
            start = max(since, base)
            lines = list(self.lines)[start - base:]
            return {"id": self.id, "project": self.project, "lines": lines, "next": self.total,
                    "dropped": max(0, base - since), "done": self.done, "results": self.results}


def create(project, label=""):
    j = Job(project, label)
    with _lock:
        _jobs[j.id] = j
        finished = [k for k, v in _jobs.items() if v.done]
        for k in finished[:-KEEP_FINISHED]:
            old = _jobs.pop(k)
            try:
                os.remove(old.path)
            except OSError:
                pass
    return j


def get(jid):
    return _jobs.get(jid)
