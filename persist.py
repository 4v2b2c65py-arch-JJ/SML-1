#!/usr/bin/env python3
"""
GMR-01 persistent atomic store — durable, crash-safe persistence with
a single-writer 'lead' lease.

- atomic_write(): tmp file + fsync + os.replace — readers never see a
  torn write; the newest complete state always 'leads'.
- LeadLease: O_EXCL lockfile with expiry — exactly one process holds
  the lead at a time; others can poll until it frees or expires.
- AtomicStore: versioned JSON documents persisted atomically, with a
  manifest recording version + writer identity.

Used for session_store.json, demand_store.json, quota_projects.json,
feed_state.json and frames.ring metadata — the 'keep it alive' layer.
"""

import json
import os
import time


def atomic_write(path, data: bytes):
    """Write bytes atomically: tmp + fsync + rename."""
    tmp = f"{path}.tmp.{os.getpid()}"
    with open(tmp, "wb") as f:
        f.write(data)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, path)
    # fsync the directory so the rename itself is durable
    try:
        dfd = os.open(os.path.dirname(os.path.abspath(path)) or ".",
                      os.O_RDONLY)
        os.fsync(dfd)
        os.close(dfd)
    except OSError:
        pass


def atomic_write_json(path, obj):
    atomic_write(path, json.dumps(obj, indent=2).encode())


class LeadLease:
    """Single-writer lead via O_EXCL lockfile with TTL expiry."""

    def __init__(self, path, ttl=30.0, owner=None):
        self.path = path
        self.ttl = ttl
        self.owner = owner or f"pid{os.getpid()}"
        self.held = False

    def _read(self):
        try:
            with open(self.path) as f:
                return json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            return None

    def acquire(self):
        """Try to take the lead. Stale leases (older than ttl) are
        stolen — a crashed leader never blocks the store forever."""
        now = time.time()
        cur = self._read()
        if cur and now - cur.get("ts", 0) < self.ttl \
                and cur.get("owner") != self.owner:
            return False
        payload = json.dumps({"owner": self.owner, "ts": now}).encode()
        try:
            fd = os.open(self.path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            os.write(fd, payload)
            os.close(fd)
            self.held = True
            return True
        except FileExistsError:
            # exists but stale (or same owner renewing) — replace
            cur = self._read()
            if cur and now - cur.get("ts", 0) >= self.ttl:
                atomic_write(self.path, payload)
                self.held = True
                return True
            if cur and cur.get("owner") == self.owner:
                atomic_write(self.path, payload)  # renew
                self.held = True
                return True
            return False

    def release(self):
        cur = self._read()
        if cur and cur.get("owner") == self.owner:
            try:
                os.unlink(self.path)
            except FileNotFoundError:
                pass
        self.held = False

    def __enter__(self):
        self.acquire()
        return self

    def __exit__(self, *a):
        self.release()


class AtomicStore:
    """Versioned JSON document with atomic persistence + lead lease."""

    def __init__(self, path, lead_path=None, owner=None):
        self.path = path
        self.lead = LeadLease(lead_path or (path + ".lead"),
                              owner=owner)
        self._doc = self._load()

    def _load(self):
        try:
            with open(self.path) as f:
                d = json.load(f)
            return d if isinstance(d, dict) else {"data": d}
        except (FileNotFoundError, json.JSONDecodeError):
            return {"version": 0, "data": {}}

    @property
    def data(self):
        return self._doc.get("data", {})

    def get(self, key, default=None):
        return self.data.get(key, default)

    def set(self, key, value):
        """Set only if this process holds the lead; otherwise the
        freshest on-disk doc wins (multi-writer safety)."""
        if self.lead.acquire():
            self._doc = self._load()          # merge freshest
            self._doc.setdefault("data", {})[key] = value
            self._doc["version"] = self._doc.get("version", 0) + 1
            self._doc["writer"] = self.lead.owner
            atomic_write_json(self.path, self._doc)
            self.lead.release()
            return True
        return False

    def update(self, fn):
        """Atomic read-modify-write under the lead lease."""
        if self.lead.acquire():
            self._doc = self._load()
            self._doc.setdefault("data", {})
            fn(self._doc["data"])
            self._doc["version"] = self._doc.get("version", 0) + 1
            self._doc["writer"] = self.lead.owner
            atomic_write_json(self.path, self._doc)
            self.lead.release()
            return True
        return False
