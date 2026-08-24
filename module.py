"""Main Persistent Priority Queue Module.

Assignment Submission: Persistent Priority Queue
File: module.py

Implements a thread-safe, double-ended priority queue with durable persistence
via an append-only Write-Ahead Log (WAL) with snapshotting or relational PostgreSQL.

Supported Operations:
  - insert(item_id, priority, data=None)
  - extract_min()
  - extract_max()
  - peek(mode='min')  [also peek_min(), peek_max()]
  - update(item_id, new_priority=None, new_data=None)
  - delete(item_id)
  - is_empty()
"""

from __future__ import annotations
import os
import threading
import uuid
from typing import Any, Dict, List, Optional, Union

from exceptions import (
    DuplicateItemError,
    EmptyQueueError,
    ItemNotFoundError,
    PriorityQueueError,
    StorageError,
)
from min_max_heap import MinMaxHeap, QueueItem
from storage import FileWALStorage, PostgresStorage, StorageEngine


class PersistentPriorityQueue:
    """Thread-safe Persistent Priority Queue supporting double-ended operations.

    Attributes:
        storage: The backing persistence engine (FileWALStorage or PostgresStorage).
        auto_checkpoint_interval: Number of operations between automatic WAL compactions.
    """

    def __init__(
        self,
        storage_dir: str = "./pq_data",
        queue_name: str = "default_queue",
        storage_engine: Optional[StorageEngine] = None,
        sync_on_write: bool = True,
        auto_checkpoint_interval: int = 500,
    ) -> None:
        """Initialize the persistent priority queue and recover previous state.

        Args:
            storage_dir: Directory to store WAL and snapshot files (for file storage).
            queue_name: Unique identifier for this queue.
            storage_engine: Custom storage engine instance. If None, FileWALStorage is used.
            sync_on_write: If True, calls fsync on every write to guarantee zero data loss.
            auto_checkpoint_interval: Interval of mutations before triggering snapshot compaction.
        """
        self._lock = threading.RLock()
        self._heap = MinMaxHeap()
        self.queue_name = queue_name
        self.auto_checkpoint_interval = auto_checkpoint_interval
        self._op_count = 0

        if storage_engine is not None:
            self.storage = storage_engine
        else:
            self.storage = FileWALStorage(
                storage_dir=storage_dir,
                queue_name=queue_name,
                sync_on_write=sync_on_write,
            )

        # Recover persisted state
        self._recover()

    def _recover(self) -> None:
        """Load and replay state from the storage engine."""
        with self._lock:
            items, seq_counter = self.storage.load_state()
            self._heap.restore_from_items(items, seq_counter=seq_counter)

    def _maybe_checkpoint(self) -> None:
        """Trigger snapshot compaction if operation threshold is reached."""
        self._op_count += 1
        if self._op_count >= self.auto_checkpoint_interval:
            self.checkpoint()
            self._op_count = 0

    # -------------------------------------------------------------------------
    # Core Assignment Operations
    # -------------------------------------------------------------------------

    def insert(
        self,
        item_id: Optional[str] = None,
        priority: float = 0.0,
        data: Any = None,
    ) -> QueueItem:
        """Insert a new element into the priority queue.

        Args:
            item_id: Unique identifier for the item. If None, a UUID is generated.
            priority: Priority value (lower value = higher priority in min-heap).
            data: Arbitrary serializable payload/metadata.

        Returns:
            The created QueueItem.

        Raises:
            DuplicateItemError: If an item with item_id already exists.
        """
        with self._lock:
            if item_id is None:
                item_id = str(uuid.uuid4())
            else:
                item_id = str(item_id)

            if item_id in self._heap:
                raise DuplicateItemError(f"Item with ID '{item_id}' already exists in queue.")

            # In-memory insertion
            item = self._heap.insert(item_id=item_id, priority=priority, data=data)

            # Persist to WAL
            self.storage.log_insert(item)
            self._maybe_checkpoint()
            return item

    def extract_min(self) -> QueueItem:
        """Remove and return the item with the minimum priority value.

        Returns:
            The extracted QueueItem.

        Raises:
            EmptyQueueError: If the queue is empty.
        """
        with self._lock:
            if self._heap.is_empty():
                raise EmptyQueueError("Cannot extract_min from an empty priority queue.")

            item = self._heap.extract_min()
            self.storage.log_extract_min(item)
            self._maybe_checkpoint()
            return item

    def extract_max(self) -> QueueItem:
        """Remove and return the item with the maximum priority value.

        Returns:
            The extracted QueueItem.

        Raises:
            EmptyQueueError: If the queue is empty.
        """
        with self._lock:
            if self._heap.is_empty():
                raise EmptyQueueError("Cannot extract_max from an empty priority queue.")

            item = self._heap.extract_max()
            self.storage.log_extract_max(item)
            self._maybe_checkpoint()
            return item

    def peek(self, mode: str = "min") -> QueueItem:
        """Inspect the top element without removing it.

        Args:
            mode: 'min' to view lowest priority item, 'max' to view highest priority item.

        Returns:
            The QueueItem at the top of the queue.

        Raises:
            EmptyQueueError: If the queue is empty.
            ValueError: If mode is not 'min' or 'max'.
        """
        with self._lock:
            if self._heap.is_empty():
                raise EmptyQueueError("Cannot peek into an empty priority queue.")

            norm_mode = mode.lower().strip()
            if norm_mode == "min":
                return self._heap.peek_min()
            elif norm_mode == "max":
                return self._heap.peek_max()
            else:
                raise ValueError(f"Invalid peek mode '{mode}'. Must be 'min' or 'max'.")

    def peek_min(self) -> QueueItem:
        """Convenience alias for peek(mode='min')."""
        return self.peek(mode="min")

    def peek_max(self) -> QueueItem:
        """Convenience alias for peek(mode='max')."""
        return self.peek(mode="max")

    def update(
        self,
        item_id: str,
        new_priority: Optional[float] = None,
        new_data: Any = None,
    ) -> QueueItem:
        """Update the priority and/or payload of an existing item.

        Args:
            item_id: The ID of the item to update.
            new_priority: The new priority value (if changing priority).
            new_data: The new payload (if provided, replaces existing payload).

        Returns:
            The updated QueueItem.

        Raises:
            ItemNotFoundError: If item_id does not exist in the queue.
        """
        with self._lock:
            str_id = str(item_id)
            if str_id not in self._heap:
                raise ItemNotFoundError(f"Cannot update: Item '{str_id}' does not exist.")

            update_data = new_data is not None
            item = self._heap.update(
                item_id=str_id,
                new_priority=new_priority,
                new_data=new_data,
                update_data=update_data,
            )
            self.storage.log_update(item)
            self._maybe_checkpoint()
            return item

    def delete(self, item_id: str) -> QueueItem:
        """Delete an arbitrary item from the queue by its ID.

        Args:
            item_id: The ID of the item to remove.

        Returns:
            The deleted QueueItem.

        Raises:
            ItemNotFoundError: If item_id does not exist in the queue.
        """
        with self._lock:
            str_id = str(item_id)
            if str_id not in self._heap:
                raise ItemNotFoundError(f"Cannot delete: Item '{str_id}' does not exist.")

            item = self._heap.delete(str_id)
            self.storage.log_delete(str_id)
            self._maybe_checkpoint()
            return item

    def is_empty(self) -> bool:
        """Check if the queue contains no items.

        Returns:
            True if empty, False otherwise.
        """
        with self._lock:
            return self._heap.is_empty()

    # -------------------------------------------------------------------------
    # Additional Utility Methods
    # -------------------------------------------------------------------------

    def __len__(self) -> int:
        with self._lock:
            return len(self._heap)

    def __contains__(self, item_id: str) -> bool:
        with self._lock:
            return str(item_id) in self._heap

    def get(self, item_id: str) -> Optional[QueueItem]:
        """Look up an item by ID without removing it."""
        with self._lock:
            return self._heap.get(str(item_id))

    def clear(self) -> None:
        """Remove all items from the queue and persist the empty state."""
        with self._lock:
            self._heap.clear()
            self.storage.log_clear()
            self.checkpoint()

    def checkpoint(self) -> None:
        """Force a snapshot checkpoint to compact WAL logs on disk."""
        with self._lock:
            items = self._heap.get_all_items()
            self.storage.checkpoint(items, self._heap._seq_counter)

    def close(self) -> None:
        """Flush and close storage resources."""
        with self._lock:
            self.checkpoint()
            self.storage.close()

    def __enter__(self) -> PersistentPriorityQueue:
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        self.close()

    def __repr__(self) -> str:
        with self._lock:
            return f"<PersistentPriorityQueue name='{self.queue_name}' size={len(self._heap)}>"


# Exports for easy import
__all__ = [
    "PersistentPriorityQueue",
    "QueueItem",
    "EmptyQueueError",
    "ItemNotFoundError",
    "DuplicateItemError",
    "StorageError",
    "PriorityQueueError",
    "FileWALStorage",
    "PostgresStorage",
]

if __name__ == "__main__":
    import shutil

    demo_dir = "./demo_pq_data"
    if os.path.exists(demo_dir):
        shutil.rmtree(demo_dir)

    print("=== Persistent Priority Queue Self-Check ===")
    pq = PersistentPriorityQueue(storage_dir=demo_dir, queue_name="demo")

    print(f"Initial is_empty(): {pq.is_empty()} (len: {len(pq)})")

    # Insert items
    pq.insert(item_id="task_critical", priority=1.0, data={"desc": "Fix security vulnerability"})
    pq.insert(item_id="task_low", priority=10.0, data={"desc": "Update documentation"})
    pq.insert(item_id="task_urgent", priority=2.5, data={"desc": "Deploy hotfix"})
    pq.insert(item_id="task_background", priority=50.0, data={"desc": "Clean temp logs"})

    print(f"After 4 inserts -> size: {len(pq)}")
    print(f"Peek Min: {pq.peek_min()}")
    print(f"Peek Max: {pq.peek_max()}")

    # Update item
    pq.update(item_id="task_low", new_priority=0.5)
    print(f"After updating 'task_low' priority to 0.5 -> New Peek Min: {pq.peek_min()}")

    # Delete item
    pq.delete("task_background")
    print(f"After deleting 'task_background' -> size: {len(pq)}")

    # Extract min and max
    min_item = pq.extract_min()
    print(f"Extracted Min: {min_item}")
    max_item = pq.extract_max()
    print(f"Extracted Max: {max_item}")

    pq.close()

    # Verify persistence by reopening
    print("\n--- Simulating Restart / Reloading Queue from Disk ---")
    pq_reloaded = PersistentPriorityQueue(storage_dir=demo_dir, queue_name="demo")
    print(f"Reloaded queue size: {len(pq_reloaded)}")
    while not pq_reloaded.is_empty():
        print(f"Drained item: {pq_reloaded.extract_min()}")

    pq_reloaded.close()
    if os.path.exists(demo_dir):
        shutil.rmtree(demo_dir)
    print("Self-check completed successfully!")
