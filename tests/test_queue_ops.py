"""Unit tests for PersistentPriorityQueue operations and API interface."""

import os
import shutil
import tempfile
import unittest

from exceptions import DuplicateItemError, EmptyQueueError, ItemNotFoundError
from module import PersistentPriorityQueue


class TestQueueOperations(unittest.TestCase):
    def setUp(self):
        self.test_dir = tempfile.mkdtemp()
        self.pq = PersistentPriorityQueue(storage_dir=self.test_dir, queue_name="test_ops")

    def tearDown(self):
        self.pq.close()
        if os.path.exists(self.test_dir):
            shutil.rmtree(self.test_dir)

    def test_initial_state(self):
        self.assertTrue(self.pq.is_empty())
        self.assertEqual(len(self.pq), 0)

    def test_insert_and_is_empty(self):
        item = self.pq.insert(item_id="job_1", priority=10.0, data={"cpu": 4})
        self.assertFalse(self.pq.is_empty())
        self.assertEqual(len(self.pq), 1)
        self.assertEqual(item.item_id, "job_1")
        self.assertEqual(item.priority, 10.0)
        self.assertEqual(item.data, {"cpu": 4})

    def test_insert_auto_generated_id(self):
        item = self.pq.insert(priority=5.0, data="test_payload")
        self.assertIsNotNone(item.item_id)
        self.assertIn(item.item_id, self.pq)

    def test_insert_duplicate_id_raises_error(self):
        self.pq.insert(item_id="unique_id", priority=1.0)
        with self.assertRaises(DuplicateItemError):
            self.pq.insert(item_id="unique_id", priority=2.0)

    def test_peek_min_and_max(self):
        self.pq.insert(item_id="low", priority=1.0)
        self.pq.insert(item_id="medium", priority=5.0)
        self.pq.insert(item_id="high", priority=10.0)

        # Default peek is min
        self.assertEqual(self.pq.peek().item_id, "low")
        self.assertEqual(self.pq.peek(mode="min").item_id, "low")
        self.assertEqual(self.pq.peek(mode="max").item_id, "high")
        self.assertEqual(self.pq.peek_min().item_id, "low")
        self.assertEqual(self.pq.peek_max().item_id, "high")

    def test_peek_invalid_mode(self):
        self.pq.insert(item_id="item_1", priority=1.0)
        with self.assertRaises(ValueError):
            self.pq.peek(mode="invalid_mode")

    def test_peek_on_empty_raises_error(self):
        with self.assertRaises(EmptyQueueError):
            self.pq.peek()
        with self.assertRaises(EmptyQueueError):
            self.pq.peek_min()
        with self.assertRaises(EmptyQueueError):
            self.pq.peek_max()

    def test_extract_min(self):
        self.pq.insert("x", 20.0)
        self.pq.insert("y", 10.0)
        self.pq.insert("z", 30.0)

        min_item = self.pq.extract_min()
        self.assertEqual(min_item.item_id, "y")
        self.assertEqual(len(self.pq), 2)
        self.assertNotIn("y", self.pq)

    def test_extract_max(self):
        self.pq.insert("x", 20.0)
        self.pq.insert("y", 10.0)
        self.pq.insert("z", 30.0)

        max_item = self.pq.extract_max()
        self.assertEqual(max_item.item_id, "z")
        self.assertEqual(len(self.pq), 2)
        self.assertNotIn("z", self.pq)

    def test_extract_on_empty_raises_error(self):
        with self.assertRaises(EmptyQueueError):
            self.pq.extract_min()
        with self.assertRaises(EmptyQueueError):
            self.pq.extract_max()

    def test_update_priority_and_data(self):
        self.pq.insert("task_a", 100.0, data={"status": "pending"})
        self.pq.insert("task_b", 50.0, data={"status": "pending"})

        # Initial min is task_b
        self.assertEqual(self.pq.peek_min().item_id, "task_b")

        # Update task_a to priority 10.0 -> should now be min
        updated = self.pq.update("task_a", new_priority=10.0, new_data={"status": "running"})
        self.assertEqual(updated.priority, 10.0)
        self.assertEqual(updated.data, {"status": "running"})
        self.assertEqual(self.pq.peek_min().item_id, "task_a")

    def test_update_non_existent_item_raises_error(self):
        with self.assertRaises(ItemNotFoundError):
            self.pq.update("ghost_id", new_priority=1.0)

    def test_delete_item(self):
        self.pq.insert("job_1", 10.0)
        self.pq.insert("job_2", 20.0)
        self.pq.insert("job_3", 30.0)

        deleted = self.pq.delete("job_2")
        self.assertEqual(deleted.item_id, "job_2")
        self.assertEqual(len(self.pq), 2)
        self.assertNotIn("job_2", self.pq)

    def test_delete_non_existent_item_raises_error(self):
        with self.assertRaises(ItemNotFoundError):
            self.pq.delete("ghost_id")

    def test_context_manager(self):
        with PersistentPriorityQueue(storage_dir=self.test_dir, queue_name="ctx_test") as ctx_pq:
            ctx_pq.insert("item_ctx", 42.0)
            self.assertEqual(len(ctx_pq), 1)


if __name__ == "__main__":
    unittest.main()
