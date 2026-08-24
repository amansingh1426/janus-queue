"""Storage Engines for Persistent Priority Queue.

Provides:
- StorageEngine: Abstract base class for persistence engines.
- FileWALStorage: High-performance Write-Ahead Log + Snapshotting file persistence.
- PostgresStorage: Relational database persistence using PostgreSQL (optional backend).
"""

from __future__ import annotations
import abc
import json
import os
import tempfile
import zlib
from typing import Any, Dict, List, Optional, Tuple

from exceptions import StorageError
from min_max_heap import QueueItem


class StorageEngine(abc.ABC):
    """Abstract interface for priority queue storage backends."""

    @abc.abstractmethod
    def log_insert(self, item: QueueItem) -> None:
        """Persist an insert operation."""
        pass

    @abc.abstractmethod
    def log_extract_min(self, item: QueueItem) -> None:
        """Persist an extract_min operation."""
        pass

    @abc.abstractmethod
    def log_extract_max(self, item: QueueItem) -> None:
        """Persist an extract_max operation."""
        pass

    @abc.abstractmethod
    def log_update(self, item: QueueItem) -> None:
        """Persist an update operation."""
        pass

    @abc.abstractmethod
    def log_delete(self, item_id: str) -> None:
        """Persist a delete operation."""
        pass

    @abc.abstractmethod
    def log_clear(self) -> None:
        """Persist a clear operation."""
        pass

    @abc.abstractmethod
    def load_state(self) -> Tuple[List[QueueItem], int]:
        """Load state and return (items, current_seq_counter)."""
        pass

    @abc.abstractmethod
    def checkpoint(self, items: List[QueueItem], seq_counter: int) -> None:
        """Save a complete snapshot to optimize recovery time."""
        pass

    @abc.abstractmethod
    def close(self) -> None:
        """Close any open file descriptors or database connections."""
        pass


class FileWALStorage(StorageEngine):
    """Write-Ahead Log (WAL) with periodic atomic snapshotting.

    Architecture:
      - Snapshot file (`<storage_dir>/<name>.snapshot.json`): Contains full serialized queue.
      - WAL file (`<storage_dir>/<name>.wal`): Append-only log of mutations with CRC32 checksums.
      - On load: Loads snapshot (if present) and replays subsequent WAL operations.
      - Crash-resilient: Corrupted partial trailing records are ignored during recovery.
    """

    def __init__(
        self,
        storage_dir: str = "./pq_data",
        queue_name: str = "default_queue",
        sync_on_write: bool = True,
        auto_checkpoint_threshold: int = 1000,
    ) -> None:
        self.storage_dir = os.path.abspath(storage_dir)
        self.queue_name = queue_name
        self.sync_on_write = sync_on_write
        self.auto_checkpoint_threshold = auto_checkpoint_threshold

        os.makedirs(self.storage_dir, exist_ok=True)
        self.wal_path = os.path.join(self.storage_dir, f"{self.queue_name}.wal")
        self.snapshot_path = os.path.join(self.storage_dir, f"{self.queue_name}.snapshot.json")

        self._wal_file = open(self.wal_path, "a+", encoding="utf-8")
        self._uncompacted_ops = 0

    def _append_wal_record(self, op_type: str, payload: Dict[str, Any]) -> None:
        """Append an atomic record with checksum to the WAL."""
        record = {
            "op": op_type,
            "payload": payload,
        }
        raw_json = json.dumps(record, separators=(",", ":"))
        checksum = zlib.crc32(raw_json.encode("utf-8")) & 0xFFFFFFFF
        line = f"{checksum:08x} {raw_json}\n"

        try:
            self._wal_file.write(line)
            if self.sync_on_write:
                self._wal_file.flush()
                os.fsync(self._wal_file.fileno())
            else:
                self._wal_file.flush()
            self._uncompacted_ops += 1
        except Exception as e:
            raise StorageError(f"Failed to write to WAL file: {e}") from e

    def log_insert(self, item: QueueItem) -> None:
        self._append_wal_record("INSERT", item.to_dict())

    def log_extract_min(self, item: QueueItem) -> None:
        self._append_wal_record("EXTRACT_MIN", {"item_id": item.item_id})

    def log_extract_max(self, item: QueueItem) -> None:
        self._append_wal_record("EXTRACT_MAX", {"item_id": item.item_id})

    def log_update(self, item: QueueItem) -> None:
        self._append_wal_record("UPDATE", item.to_dict())

    def log_delete(self, item_id: str) -> None:
        self._append_wal_record("DELETE", {"item_id": str(item_id)})

    def log_clear(self) -> None:
        self._append_wal_record("CLEAR", {})

    def checkpoint(self, items: List[QueueItem], seq_counter: int) -> None:
        """Write an atomic snapshot file and truncate the WAL."""
        snapshot_data = {
            "queue_name": self.queue_name,
            "seq_counter": seq_counter,
            "items": [item.to_dict() for item in items],
        }

        # Write to temporary file first for atomic replacement
        temp_fd, temp_path = tempfile.mkstemp(dir=self.storage_dir, prefix="snapshot_tmp_")
        try:
            with os.fdopen(temp_fd, "w", encoding="utf-8") as f:
                json.dump(snapshot_data, f, indent=2)
                f.flush()
                os.fsync(f.fileno())

            # Atomic replace
            os.replace(temp_path, self.snapshot_path)

            # Truncate WAL
            self._wal_file.close()
            self._wal_file = open(self.wal_path, "w", encoding="utf-8")
            self._wal_file.flush()
            os.fsync(self._wal_file.fileno())
            self._wal_file.close()
            self._wal_file = open(self.wal_path, "a+", encoding="utf-8")
            self._uncompacted_ops = 0
        except Exception as e:
            if os.path.exists(temp_path):
                os.remove(temp_path)
            raise StorageError(f"Failed to create checkpoint snapshot: {e}") from e

    def load_state(self) -> Tuple[List[QueueItem], int]:
        """Recover state from snapshot + WAL log replay."""
        items_map: Dict[str, QueueItem] = {}
        seq_counter = 0

        # Step 1: Load base snapshot if present
        if os.path.exists(self.snapshot_path):
            try:
                with open(self.snapshot_path, "r", encoding="utf-8") as f:
                    snap = json.load(f)
                    seq_counter = snap.get("seq_counter", 0)
                    for raw_item in snap.get("items", []):
                        item = QueueItem.from_dict(raw_item)
                        items_map[item.item_id] = item
            except Exception as e:
                raise StorageError(f"Failed to read snapshot file '{self.snapshot_path}': {e}") from e

        # Step 2: Replay WAL entries
        if os.path.exists(self.wal_path):
            with open(self.wal_path, "r", encoding="utf-8") as f:
                for line_no, raw_line in enumerate(f, start=1):
                    line = raw_line.strip()
                    if not line:
                        continue
                    parts = line.split(" ", 1)
                    if len(parts) != 2:
                        # Malformed or truncated trailing line, skip
                        continue
                    expected_crc_hex, json_str = parts
                    try:
                        expected_crc = int(expected_crc_hex, 16)
                    except ValueError:
                        continue

                    actual_crc = zlib.crc32(json_str.encode("utf-8")) & 0xFFFFFFFF
                    if expected_crc != actual_crc:
                        # Corrupted line detected, ignore trailing corruption
                        continue

                    try:
                        entry = json.loads(json_str)
                    except json.JSONDecodeError:
                        continue

                    op = entry.get("op")
                    payload = entry.get("payload", {})

                    if op == "INSERT":
                        item = QueueItem.from_dict(payload)
                        items_map[item.item_id] = item
                        if item.seq > seq_counter:
                            seq_counter = item.seq
                    elif op == "UPDATE":
                        item = QueueItem.from_dict(payload)
                        items_map[item.item_id] = item
                    elif op in ("EXTRACT_MIN", "EXTRACT_MAX", "DELETE"):
                        target_id = str(payload.get("item_id"))
                        items_map.pop(target_id, None)
                    elif op == "CLEAR":
                        items_map.clear()

        return list(items_map.values()), seq_counter

    def close(self) -> None:
        """Flush and close WAL file."""
        if hasattr(self, "_wal_file") and not self._wal_file.closed:
            self._wal_file.flush()
            try:
                os.fsync(self._wal_file.fileno())
            except OSError:
                pass
            self._wal_file.close()


class PostgresStorage(StorageEngine):
    """PostgreSQL relational persistence engine.

    Requires psycopg2 or psycopg3 library and active database connection string.
    """

    def __init__(
        self,
        connection_uri: str,
        table_name: str = "persistent_priority_queue",
    ) -> None:
        self.connection_uri = connection_uri
        self.table_name = table_name
        self._conn = None
        self._init_db()

    def _get_connection(self):
        try:
            import psycopg2
            if self._conn is None or self._conn.closed:
                self._conn = psycopg2.connect(self.connection_uri)
            return self._conn
        except ImportError as e:
            raise StorageError(
                "psycopg2 is required for PostgresStorage. Install with 'pip install psycopg2-binary'."
            ) from e
        except Exception as e:
            raise StorageError(f"PostgreSQL connection error: {e}") from e

    def _init_db(self) -> None:
        """Create table and index if they do not exist."""
        conn = self._get_connection()
        with conn.cursor() as cur:
            cur.execute(f"""
                CREATE TABLE IF NOT EXISTS {self.table_name} (
                    item_id VARCHAR(255) PRIMARY KEY,
                    priority DOUBLE PRECISION NOT NULL,
                    seq BIGINT NOT NULL,
                    data JSONB
                );
                CREATE INDEX IF NOT EXISTS idx_{self.table_name}_priority
                ON {self.table_name} (priority ASC, seq ASC);
            """)
        conn.commit()

    def log_insert(self, item: QueueItem) -> None:
        conn = self._get_connection()
        with conn.cursor() as cur:
            cur.execute(f"""
                INSERT INTO {self.table_name} (item_id, priority, seq, data)
                VALUES (%s, %s, %s, %s)
                ON CONFLICT (item_id) DO UPDATE
                SET priority = EXCLUDED.priority, seq = EXCLUDED.seq, data = EXCLUDED.data;
            """, (item.item_id, item.priority, item.seq, json.dumps(item.data)))
        conn.commit()

    def log_extract_min(self, item: QueueItem) -> None:
        self.log_delete(item.item_id)

    def log_extract_max(self, item: QueueItem) -> None:
        self.log_delete(item.item_id)

    def log_update(self, item: QueueItem) -> None:
        self.log_insert(item)

    def log_delete(self, item_id: str) -> None:
        conn = self._get_connection()
        with conn.cursor() as cur:
            cur.execute(f"DELETE FROM {self.table_name} WHERE item_id = %s;", (str(item_id),))
        conn.commit()

    def log_clear(self) -> None:
        conn = self._get_connection()
        with conn.cursor() as cur:
            cur.execute(f"TRUNCATE TABLE {self.table_name};")
        conn.commit()

    def load_state(self) -> Tuple[List[QueueItem], int]:
        conn = self._get_connection()
        items = []
        max_seq = 0
        with conn.cursor() as cur:
            cur.execute(f"SELECT item_id, priority, seq, data FROM {self.table_name};")
            for row in cur.fetchall():
                item_id, priority, seq, data = row
                if isinstance(data, str):
                    try:
                        data = json.loads(data)
                    except json.JSONDecodeError:
                        pass
                items.append(QueueItem(item_id=str(item_id), priority=float(priority), seq=int(seq), data=data))
                if seq > max_seq:
                    max_seq = seq
        return items, max_seq

    def checkpoint(self, items: List[QueueItem], seq_counter: int) -> None:
        # Relational database is already continuously consistent
        pass

    def close(self) -> None:
        if self._conn is not None and not self._conn.closed:
            self._conn.close()
