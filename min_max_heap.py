"""Indexed Min-Max Heap Implementation for Double-Ended Priority Queues.

A Min-Max Heap is a complete binary tree stored in an array where alternating
levels represent Min and Max tiers:
  - Level 0 (Root): Min level
  - Level 1: Max level
  - Level 2: Min level
  - Level 3: Max level
  ...

This data structure provides:
  - O(1) peek_min
  - O(1) peek_max
  - O(log N) insert
  - O(log N) extract_min
  - O(log N) extract_max
  - O(log N) arbitrary update (via index map)
  - O(log N) arbitrary delete (via index map)
"""

from __future__ import annotations
import math
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

from exceptions import EmptyQueueError, ItemNotFoundError, DuplicateItemError


@dataclass
class QueueItem:
    """Represents an item in the Priority Queue."""
    item_id: str
    priority: float
    seq: int = 0
    data: Any = None

    def sort_key(self) -> Tuple[float, int]:
        """Comparison key using priority with sequence tie-breaker."""
        return (self.priority, self.seq)

    def to_dict(self) -> Dict[str, Any]:
        """Convert item to dictionary for serialization."""
        return {
            "item_id": self.item_id,
            "priority": self.priority,
            "seq": self.seq,
            "data": self.data,
        }

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> QueueItem:
        """Create a QueueItem from a dictionary."""
        return cls(
            item_id=str(d["item_id"]),
            priority=float(d["priority"]),
            seq=int(d.get("seq", 0)),
            data=d.get("data"),
        )


class MinMaxHeap:
    """An indexed Double-Ended Priority Queue implemented as a Min-Max Heap.

    Maintains an auxiliary hash table mapping `item_id` -> `heap_index` to allow
    O(log N) updates and deletions.
    """

    def __init__(self) -> None:
        self._heap: List[QueueItem] = []
        self._pos_map: Dict[str, int] = {}
        self._seq_counter: int = 0

    def __len__(self) -> int:
        return len(self._heap)

    def is_empty(self) -> bool:
        """Check if the heap is empty."""
        return len(self._heap) == 0

    def __contains__(self, item_id: str) -> bool:
        return str(item_id) in self._pos_map

    def get(self, item_id: str) -> Optional[QueueItem]:
        """Get an item by ID without removing it."""
        idx = self._pos_map.get(str(item_id))
        if idx is not None:
            return self._heap[idx]
        return None

    def get_all_items(self) -> List[QueueItem]:
        """Return a copy of all items currently in the heap."""
        return list(self._heap)

    # -------------------------------------------------------------------------
    # Internal Heap Helpers
    # -------------------------------------------------------------------------

    @staticmethod
    def _is_min_level(idx: int) -> bool:
        """Return True if index is on a min-level, False for max-level."""
        level = int(math.floor(math.log2(idx + 1)))
        return (level % 2) == 0

    def _swap(self, i: int, j: int) -> None:
        """Swap elements at indices i and j, keeping the position map synchronized."""
        item_i, item_j = self._heap[i], self._heap[j]
        self._heap[i], self._heap[j] = item_j, item_i
        self._pos_map[item_i.item_id] = j
        self._pos_map[item_j.item_id] = i

    def _lt(self, i: int, j: int) -> bool:
        """Return True if item at index i has strictly lower priority than index j."""
        return self._heap[i].sort_key() < self._heap[j].sort_key()

    def _gt(self, i: int, j: int) -> bool:
        """Return True if item at index i has strictly higher priority than index j."""
        return self._heap[i].sort_key() > self._heap[j].sort_key()

    # -------------------------------------------------------------------------
    # Heapify Up (Push Up)
    # -------------------------------------------------------------------------

    def _push_up(self, idx: int) -> None:
        """Push an element up to restore Min-Max heap properties."""
        if idx == 0:
            return

        parent = (idx - 1) // 2
        if self._is_min_level(idx):
            if self._gt(idx, parent):
                self._swap(idx, parent)
                self._push_up_max(parent)
            else:
                self._push_up_min(idx)
        else:
            if self._lt(idx, parent):
                self._swap(idx, parent)
                self._push_up_min(parent)
            else:
                self._push_up_max(idx)

    def _push_up_min(self, idx: int) -> None:
        """Push up along min levels."""
        parent = (idx - 1) // 2
        if parent > 0:
            grandparent = (parent - 1) // 2
            if self._lt(idx, grandparent):
                self._swap(idx, grandparent)
                self._push_up_min(grandparent)

    def _push_up_max(self, idx: int) -> None:
        """Push up along max levels."""
        parent = (idx - 1) // 2
        if parent > 0:
            grandparent = (parent - 1) // 2
            if self._gt(idx, grandparent):
                self._swap(idx, grandparent)
                self._push_up_max(grandparent)

    # -------------------------------------------------------------------------
    # Heapify Down (Push Down)
    # -------------------------------------------------------------------------

    def _push_down(self, idx: int) -> None:
        """Push an element down to restore Min-Max heap properties."""
        if self._is_min_level(idx):
            self._push_down_min(idx)
        else:
            self._push_down_max(idx)

    def _get_descendants(self, idx: int) -> Tuple[List[int], List[int]]:
        """Return (children_indices, grandchildren_indices) for a given node."""
        n = len(self._heap)
        children = []
        grandchildren = []

        c1 = 2 * idx + 1
        c2 = 2 * idx + 2

        if c1 < n:
            children.append(c1)
            g1 = 2 * c1 + 1
            g2 = 2 * c1 + 2
            if g1 < n:
                grandchildren.append(g1)
            if g2 < n:
                grandchildren.append(g2)

        if c2 < n:
            children.append(c2)
            g3 = 2 * c2 + 1
            g4 = 2 * c2 + 2
            if g3 < n:
                grandchildren.append(g3)
            if g4 < n:
                grandchildren.append(g4)

        return children, grandchildren

    def _push_down_min(self, idx: int) -> None:
        """Push down along min levels."""
        children, grandchildren = self._get_descendants(idx)
        candidates = children + grandchildren
        if not candidates:
            return

        # Find candidate with smallest key
        min_idx = candidates[0]
        for c in candidates[1:]:
            if self._lt(c, min_idx):
                min_idx = c

        if min_idx in grandchildren:
            if self._lt(min_idx, idx):
                self._swap(min_idx, idx)
                parent = (min_idx - 1) // 2
                if self._gt(min_idx, parent):
                    self._swap(min_idx, parent)
                self._push_down_min(min_idx)
        else:
            # min_idx is a direct child
            if self._lt(min_idx, idx):
                self._swap(min_idx, idx)

    def _push_down_max(self, idx: int) -> None:
        """Push down along max levels."""
        children, grandchildren = self._get_descendants(idx)
        candidates = children + grandchildren
        if not candidates:
            return

        # Find candidate with largest key
        max_idx = candidates[0]
        for c in candidates[1:]:
            if self._gt(c, max_idx):
                max_idx = c

        if max_idx in grandchildren:
            if self._gt(max_idx, idx):
                self._swap(max_idx, idx)
                parent = (max_idx - 1) // 2
                if self._lt(max_idx, parent):
                    self._swap(max_idx, parent)
                self._push_down_max(max_idx)
        else:
            # max_idx is a direct child
            if self._gt(max_idx, idx):
                self._swap(max_idx, idx)

    # -------------------------------------------------------------------------
    # Public Operations
    # -------------------------------------------------------------------------

    def insert(self, item_id: str, priority: float, data: Any = None, seq: Optional[int] = None) -> QueueItem:
        """Insert a new item with given priority and optional payload.

        Time Complexity: O(log N)
        """
        str_id = str(item_id)
        if str_id in self._pos_map:
            raise DuplicateItemError(f"Item with ID '{str_id}' already exists in queue.")

        if seq is None:
            self._seq_counter += 1
            seq = self._seq_counter
        else:
            if seq >= self._seq_counter:
                self._seq_counter = seq + 1

        item = QueueItem(item_id=str_id, priority=float(priority), seq=seq, data=data)
        idx = len(self._heap)
        self._heap.append(item)
        self._pos_map[str_id] = idx
        self._push_up(idx)
        return item

    def peek_min(self) -> QueueItem:
        """Return the minimum priority item without removing it.

        Time Complexity: O(1)
        """
        if self.is_empty():
            raise EmptyQueueError("Cannot peek into an empty priority queue.")
        return self._heap[0]

    def peek_max(self) -> QueueItem:
        """Return the maximum priority item without removing it.

        Time Complexity: O(1)
        """
        if self.is_empty():
            raise EmptyQueueError("Cannot peek into an empty priority queue.")
        n = len(self._heap)
        if n == 1:
            return self._heap[0]
        if n == 2:
            return self._heap[1]
        return self._heap[1] if self._gt(1, 2) else self._heap[2]

    def extract_min(self) -> QueueItem:
        """Remove and return the minimum priority item.

        Time Complexity: O(log N)
        """
        if self.is_empty():
            raise EmptyQueueError("Cannot extract min from an empty priority queue.")

        min_item = self._heap[0]
        last_item = self._heap.pop()
        del self._pos_map[min_item.item_id]

        if self._heap:
            self._heap[0] = last_item
            self._pos_map[last_item.item_id] = 0
            self._push_down(0)

        return min_item

    def extract_max(self) -> QueueItem:
        """Remove and return the maximum priority item.

        Time Complexity: O(log N)
        """
        if self.is_empty():
            raise EmptyQueueError("Cannot extract max from an empty priority queue.")

        n = len(self._heap)
        if n == 1:
            max_item = self._heap.pop()
            del self._pos_map[max_item.item_id]
            return max_item

        max_idx = 1
        if n > 2 and self._gt(2, 1):
            max_idx = 2

        max_item = self._heap[max_idx]
        last_item = self._heap.pop()
        del self._pos_map[max_item.item_id]

        if max_idx < len(self._heap):
            self._heap[max_idx] = last_item
            self._pos_map[last_item.item_id] = max_idx
            self._push_down(max_idx)

        return max_item

    def delete(self, item_id: str) -> QueueItem:
        """Remove an item by ID from anywhere in the queue.

        Time Complexity: O(log N)
        """
        str_id = str(item_id)
        if str_id not in self._pos_map:
            raise ItemNotFoundError(f"Item with ID '{str_id}' not found in queue.")

        idx = self._pos_map[str_id]
        target_item = self._heap[idx]
        last_item = self._heap.pop()
        del self._pos_map[str_id]

        if idx < len(self._heap):
            self._heap[idx] = last_item
            self._pos_map[last_item.item_id] = idx
            # Rebalance from current position of last_item
            self._push_down(self._pos_map[last_item.item_id])
            self._push_up(self._pos_map[last_item.item_id])

        return target_item

    def update(
        self,
        item_id: str,
        new_priority: Optional[float] = None,
        new_data: Any = None,
        update_data: bool = False,
    ) -> QueueItem:
        """Update the priority and/or payload of an existing item.

        Time Complexity: O(log N)
        """
        str_id = str(item_id)
        if str_id not in self._pos_map:
            raise ItemNotFoundError(f"Item with ID '{str_id}' not found in queue.")

        idx = self._pos_map[str_id]
        item = self._heap[idx]

        if new_priority is not None:
            item.priority = float(new_priority)
        if update_data:
            item.data = new_data

        # Rebalance heap: try push up first, then push down
        self._push_up(self._pos_map[str_id])
        self._push_down(self._pos_map[str_id])
        return item

    def clear(self) -> None:
        """Clear all elements from the heap."""
        self._heap.clear()
        self._pos_map.clear()
        self._seq_counter = 0

    def restore_from_items(self, items: List[QueueItem], seq_counter: int = 0) -> None:
        """Rebuild the heap from a list of items."""
        self.clear()
        self._seq_counter = seq_counter
        for it in items:
            self.insert(item_id=it.item_id, priority=it.priority, data=it.data, seq=it.seq)
