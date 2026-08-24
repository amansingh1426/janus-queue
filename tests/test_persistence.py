"""Unit tests for persistence, snapshotting, and crash recovery."""

import os
import shutil
import tempfile
import unittest

from module import PersistentPriorityQueue


class TestPersistence(unittest.TestCase):
    def setUp(self):
        self.test_dir = tempfile.mkdtemp()

    def tearDown(self):
        if os.path.exists(self.test_dir):
            shutil.rmtree(self.test_dir)

    def test_state_recovery_across_restarts(self):
        # Session 1: Populate queue
        pq1 = PersistentPriorityQueue(storage_dir=self.test_dir, queue_name="persist_test")
        pq1.insert("t1", 50.0, data={"step": 1})
        pq1.insert("t2", 10.0, data={"step": 2})
        pq1.insert("t3", 30.0, data={"step": 3})
        pq1.update("t1", new_priority=5.0)  # t1 is now lowest (5.0)
        pq1.delete("t3")                     # delete t3
        pq1.close()

        # Session 2: Reload from disk
        pq2 = PersistentPriorityQueue(storage_dir=self.test_dir, queue_name="persist_test")
        self.assertEqual(len(pq2), 2)
        self.assertIn("t1", pq2)
        self.assertIn("t2", pq2)
        self.assertNotIn("t3", pq2)

        # Verify ordering is intact
        min_item = pq2.extract_min()
        self.assertEqual(min_item.item_id, "t1")
        self.assertEqual(min_item.priority, 5.0)

        next_item = pq2.extract_min()
        self.assertEqual(next_item.item_id, "t2")
        self.assertEqual(next_item.priority, 10.0)

        self.assertTrue(pq2.is_empty())
        pq2.close()

    def test_snapshot_checkpointing(self):
        pq = PersistentPriorityQueue(
            storage_dir=self.test_dir,
            queue_name="snap_test",
            auto_checkpoint_interval=5,
        )

        for i in range(10):
            pq.insert(f"item_{i}", float(i))

        # Checkpoint should have run automatically
        snapshot_file = os.path.join(self.test_dir, "snap_test.snapshot.json")
        self.assertTrue(os.path.exists(snapshot_file))

        pq.close()

        # Reopen and check integrity
        pq_reopen = PersistentPriorityQueue(storage_dir=self.test_dir, queue_name="snap_test")
        self.assertEqual(len(pq_reopen), 10)
        self.assertEqual(pq_reopen.peek_min().item_id, "item_0")
        self.assertEqual(pq_reopen.peek_max().item_id, "item_9")
        pq_reopen.close()

    def test_crash_recovery_with_corrupted_trailing_bytes(self):
        # Session 1: Normal writes
        pq1 = PersistentPriorityQueue(storage_dir=self.test_dir, queue_name="crash_test")
        pq1.insert("valid_1", 10.0)
        pq1.insert("valid_2", 20.0)
        pq1.close()

        # Simulate sudden power cut while appending a corrupt line to WAL
        wal_path = os.path.join(self.test_dir, "crash_test.wal")
        with open(wal_path, "a", encoding="utf-8") as f:
            f.write("bad_crc_hex {\"op\":\"INSERT\",\"payload\":{\"item_id\":\"corrupt_half_line\n")

        # Session 2: Queue should cleanly recover up to the last valid record
        pq2 = PersistentPriorityQueue(storage_dir=self.test_dir, queue_name="crash_test")
        self.assertEqual(len(pq2), 2)
        self.assertIn("valid_1", pq2)
        self.assertIn("valid_2", pq2)
        self.assertNotIn("corrupt_half_line", pq2)
        pq2.close()


if __name__ == "__main__":
    unittest.main()
