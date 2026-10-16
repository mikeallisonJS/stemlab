"""
The job queue behind the API: runs recipes one at a time on a worker thread
and keeps every event so clients can replay and follow a run.

Jobs go through the runner like the CLI does; nothing here touches a backend.
"""

from __future__ import annotations

import asyncio
import json
import threading
import time
import uuid
from collections import deque
from pathlib import Path
from typing import Any

from stemlab import runner
from stemlab.backends.base import Cancelled
from stemlab.recipe import MIX, Recipe
from stemlab.registry import Registry

QUEUED, RUNNING, FINISHED, FAILED, CANCELLED = "queued", "running", "finished", "failed", "cancelled"
ACTIVE = (QUEUED, RUNNING)


class Job:
    """One recipe run on one input file."""

    def __init__(
        self,
        recipe: Recipe,
        input_path: Path,
        out_dir: Path | None,
        use_cache: bool,
        out_parent: Path | None = None,
    ):
        self.id = uuid.uuid4().hex[:12]
        self.recipe = recipe
        self.input_path = input_path
        self.out_dir = out_dir
        #: Without an explicit folder, the run creates one below this (next to the input when None)
        self.out_parent = out_parent
        self.use_cache = use_cache
        self.status = QUEUED
        self.created = time.time()
        self.started: float | None = None
        self.finished: float | None = None
        self.error: str | None = None
        self.record: dict | None = None
        self.cancel = threading.Event()
        self.events: list[dict] = []
        self.order = recipe.order()
        self.nodes: dict[str, dict] = {
            name: {
                "op": recipe.nodes[name].op,
                "model": getattr(recipe.nodes[name], "model", None),
                "status": "waiting",
                "fraction": 0.0,
                "message": "",
                "stems": {},
                "info": {},
            }
            for name in self.order
        }
        self.mix_file: str | None = None
        self._lock = threading.Lock()
        self._subscribers: list[tuple[asyncio.AbstractEventLoop, asyncio.Queue]] = []

    # State ---------------------------------------------------------------------

    def apply(self, event: dict) -> None:
        """Update the job's state from a runner event and pass the event on."""
        kind = event.get("type")
        node = self.nodes.get(event.get("node", ""))
        if kind == "node_started" and node:
            node.update(status="running", fraction=0.0)
        elif kind == "node_status" and node:
            node["message"] = event.get("status", "")
        elif kind == "node_progress" and node:
            node["fraction"] = event["fraction"]
        elif kind == "node_finished" and node:
            node.update(
                status="cached" if event.get("cached") else "done",
                fraction=1.0,
                message="",
                seconds=event.get("seconds"),
                stems=event.get("stems", {}),
                info=event.get("info", {}),
            )
        elif kind == "warning" and node:
            node.setdefault("warnings", []).append(event.get("message", ""))
        self.publish(event)

    def publish(self, event: dict) -> None:
        event = {**event, "job_id": self.id, "seq": len(self.events)}
        with self._lock:
            self.events.append(event)
            subscribers = list(self._subscribers)
        for loop, queue in subscribers:
            loop.call_soon_threadsafe(queue.put_nowait, event)

    def subscribe(self, loop: asyncio.AbstractEventLoop) -> tuple[asyncio.Queue, list[dict]]:
        """Start following the job. Returns a queue of new events and the ones so far."""
        queue: asyncio.Queue = asyncio.Queue()
        with self._lock:
            self._subscribers.append((loop, queue))
            return queue, list(self.events)

    def unsubscribe(self, queue: asyncio.Queue) -> None:
        with self._lock:
            self._subscribers = [(loop, q) for loop, q in self._subscribers if q is not queue]

    @property
    def done(self) -> bool:
        return self.status not in ACTIVE

    def stem_file(self, node: str, stem: str) -> str | None:
        """Path of a stem's cached audio, available as soon as its node has finished."""
        if node == MIX:
            return self.mix_file
        return (self.nodes.get(node) or {}).get("stems", {}).get(stem)

    def summary(self) -> dict:
        return {
            "id": self.id,
            "status": self.status,
            "recipe": self.recipe.name,
            "input": str(self.input_path),
            "track": self.input_path.stem,
            "created": self.created,
            "started": self.started,
            "finished": self.finished,
            "error": self.error,
            "order": self.order,
            "nodes": self.nodes,
            "has_mix": self.mix_file is not None,
            "output_dir": (self.record or {}).get("output_dir") or (str(self.out_dir) if self.out_dir else None),
            "outputs": (self.record or {}).get("outputs", []),
            "warnings": (self.record or {}).get("warnings", []),
            "seconds": (self.record or {}).get("seconds"),
        }

    def detail(self) -> dict:
        return {
            **self.summary(),
            "recipe_data": self.recipe.model_dump(mode="json", exclude_defaults=True),
            "record": self.record,
        }


class JobManager:
    """Queues jobs and runs them one after another: the GPU is not shared between runs."""

    def __init__(self, registry_factory=Registry, keep: int = 200):
        self.registry_factory = registry_factory
        self.jobs: dict[str, Job] = {}
        self.keep = keep
        self._queue: deque[Job] = deque()
        self._condition = threading.Condition()
        self._stopping = False
        self._thread = threading.Thread(target=self._work, name="stemlab-jobs", daemon=True)
        self._thread.start()

    def submit(
        self,
        recipe: Recipe,
        input_path: Path,
        out_dir: Path | None = None,
        use_cache: bool = True,
        out_parent: Path | None = None,
    ) -> Job:
        job = Job(recipe, input_path, out_dir, use_cache, out_parent)
        with self._condition:
            self.jobs[job.id] = job
            self._queue.append(job)
            self._forget_old()
            self._condition.notify()
        job.publish({"type": "job_queued"})
        return job

    def open_run(self, run_json: Path) -> Job:
        """Register a finished run from its run.json, to look at its results again."""
        from stemlab.recipe import parse

        record = json.loads(Path(run_json).read_text(encoding="utf-8"))
        if "recipe" not in record or "nodes" not in record:
            raise ValueError(f"{run_json} is not a run.json")
        job = Job(parse(record["recipe"]), Path(record["input"]["path"]), Path(record["output_dir"]), True)
        job.status = FINISHED
        job.record = record
        job.mix_file = (record.get("mix") or {}).get("file")
        for name, entry in record["nodes"].items():
            if name in job.nodes:
                job.nodes[name].update(
                    status="cached" if entry.get("cached") else "done",
                    fraction=1.0,
                    seconds=entry.get("seconds"),
                    stems=entry.get("stems", {}),
                    info=entry.get("info", {}),
                )
        with self._condition:
            self.jobs[job.id] = job
        return job

    def get(self, job_id: str) -> Job | None:
        return self.jobs.get(job_id)

    def list(self) -> list[Job]:
        return sorted(self.jobs.values(), key=lambda job: job.created)

    def cancel(self, job_id: str) -> bool:
        job = self.jobs.get(job_id)
        if job is None or job.done:
            return False
        job.cancel.set()
        with self._condition:
            if job in self._queue:
                # Never started: nothing else will report its end
                self._queue.remove(job)
                self._finish_cancelled(job)
        return True

    @staticmethod
    def _finish_cancelled(job: Job) -> None:
        """End a job that was cancelled before it ran. Followers wait for `job_done`."""
        job.status = CANCELLED
        job.finished = time.time()
        job.publish({"type": "run_cancelled"})
        job.publish({"type": "job_done", "status": CANCELLED})

    def remove(self, job_id: str) -> bool:
        """Forget a job that is no longer running."""
        job = self.jobs.get(job_id)
        if job is None or not job.done:
            return False
        del self.jobs[job_id]
        return True

    def shutdown(self) -> None:
        with self._condition:
            self._stopping = True
            for job in self.jobs.values():
                job.cancel.set()
            self._condition.notify_all()
        self._thread.join(timeout=30)

    def _forget_old(self) -> None:
        finished = [job for job in self.list() if job.done]
        for job in finished[: max(0, len(self.jobs) - self.keep)]:
            del self.jobs[job.id]

    def _work(self) -> None:
        while True:
            with self._condition:
                while not self._queue and not self._stopping:
                    self._condition.wait()
                if self._stopping:
                    return
                job = self._queue.popleft()
            self._run(job)

    def _run(self, job: Job) -> None:
        if job.cancel.is_set():
            # Cancelled in the moment between leaving the queue and starting
            if not job.done:
                self._finish_cancelled(job)
            return
        job.status = RUNNING
        job.started = time.time()

        def on_event(event: dict[str, Any]) -> None:
            if event.get("type") == "run_started":
                job.out_dir = Path(event["output_dir"])
            job.apply(event)

        try:
            # The registry is read fresh for every job, so newly added models are seen
            registry = self.registry_factory()
            job.record = runner.run_recipe(
                job.recipe,
                job.input_path,
                job.out_dir,
                registry=registry,
                events=on_event,
                cancel=job.cancel,
                use_cache=job.use_cache,
                on_mix=lambda path: setattr(job, "mix_file", path),
                out_parent=job.out_parent,
            )
            job.status = FINISHED
        except Cancelled:
            job.status = CANCELLED
        except Exception as e:
            job.status = FAILED
            job.error = str(e) or type(e).__name__
            for node in job.nodes.values():
                if node["status"] == "running":
                    node["status"] = "failed"
            # Problems found before the run starts never reach the runner's own events
            if not any(event["type"] == "run_failed" for event in job.events):
                job.publish({"type": "run_failed", "error": job.error})
        finally:
            job.finished = time.time()
            job.publish({"type": "job_done", "status": job.status})
