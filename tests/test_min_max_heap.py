"""Unit tests for Indexed MinMaxHeap."""

import random
import unittest
from exceptions import DuplicateItemError, EmptyQueueError, ItemNotFoundError
from min_max_heap import MinMaxHeap, QueueItem


class TestMinMaxHeap(unittest.TestCase):
    def setUp(self):
        self.heap = MinMaxHeap()

    def test_empty_heap(self):
        self.assertTrue(self.heap.is_empty())
        self.assertEqual(len(self.heap), 0)
        with self.assertRaises(EmptyQueueError):
            self.heap.peek_min()
        with self.assertRaises(EmptyQueueError):
            self.heap.peek_max()
        with self.assertRaises(EmptyQueueError):
            self.heap.extract_min()
        with self.assertRaises(EmptyQueueError):
            self.heap.extract_max()

    def test_single_element(self):
        self.heap.insert("a", 10.0, data="data_a")
        self.assertFalse(self.heap.is_empty())
        self.assertEqual(len(self.heap), 1)
        self.assertEqual(self.heap.peek_min().item_id, "a")
        self.assertEqual(self.heap.peek_max().item_id, "a")

        item = self.heap.extract_min()
        self.assertEqual(item.item_id, "a")
        self.assertEqual(item.priority, 10.0)
        self.assertTrue(self.heap.is_empty())

    def test_two_elements(self):
        self.heap.insert("a", 10.0)
        self.heap.insert("b", 20.0)
        self.assertEqual(self.heap.peek_min().item_id, "a")
        self.assertEqual(self.heap.peek_max().item_id, "b")

        self.assertEqual(self.heap.extract_max().item_id, "b")
        self.assertEqual(self.heap.extract_min().item_id, "a")
        self.assertTrue(self.heap.is_empty())

    def test_three_elements(self):
        self.heap.insert("a", 15.0)
        self.heap.insert("b", 5.0)
        self.heap.insert("c", 25.0)
        self.assertEqual(self.heap.peek_min().item_id, "b")
        self.assertEqual(self.heap.peek_max().item_id, "c")

        self.assertEqual(self.heap.extract_min().item_id, "b")
        self.assertEqual(self.heap.extract_min().item_id, "a")
        self.assertEqual(self.heap.extract_min().item_id, "c")
        self.assertTrue(self.heap.is_empty())

    def test_duplicate_id_rejection(self):
        self.heap.insert("id_1", 10.0)
        with self.assertRaises(DuplicateItemError):
            self.heap.insert("id_1", 20.0)

    def test_sorted_min_extraction_random_array(self):
        nums = [random.uniform(-1000, 1000) for _ in range(200)]
        for i, val in enumerate(nums):
            self.heap.insert(f"item_{i}", val)

        extracted = []
        while not self.heap.is_empty():
            extracted.append(self.heap.extract_min().priority)

        self.assertEqual(extracted, sorted(nums))

    def test_sorted_max_extraction_random_array(self):
        nums = [random.uniform(-1000, 1000) for _ in range(200)]
        for i, val in enumerate(nums):
            self.heap.insert(f"item_{i}", val)

        extracted = []
        while not self.heap.is_empty():
            extracted.append(self.heap.extract_max().priority)

        self.assertEqual(extracted, sorted(nums, reverse=True))

    def test_interleaved_min_max_extractions(self):
        values = [50, 10, 80, 20, 70, 30, 60, 40]
        for i, val in enumerate(values):
            self.heap.insert(f"k_{i}", float(val))

        # Min -> 10, Max -> 80, Min -> 20, Max -> 70
        self.assertEqual(self.heap.extract_min().priority, 10.0)
        self.assertEqual(self.heap.extract_max().priority, 80.0)
        self.assertEqual(self.heap.extract_min().priority, 20.0)
        self.assertEqual(self.heap.extract_max().priority, 70.0)
        self.assertEqual(self.heap.extract_min().priority, 30.0)
        self.assertEqual(self.heap.extract_max().priority, 60.0)
        self.assertEqual(self.heap.extract_min().priority, 40.0)
        self.assertEqual(self.heap.extract_max().priority, 50.0)
        self.assertTrue(self.heap.is_empty())

    def test_fifo_tie_breaking(self):
        # Items with same priority should be extracted in FIFO insertion order
        self.heap.insert("task_1", 5.0)
        self.heap.insert("task_2", 5.0)
        self.heap.insert("task_3", 5.0)

        self.assertEqual(self.heap.extract_min().item_id, "task_1")
        self.assertEqual(self.heap.extract_min().item_id, "task_2")
        self.assertEqual(self.heap.extract_min().item_id, "task_3")

    def test_arbitrary_delete(self):
        items = [("a", 10), ("b", 20), ("c", 30), ("d", 40), ("e", 50), ("f", 5)]
        for k, v in items:
            self.heap.insert(k, float(v))

        # Delete root (f: 5)
        del_item = self.heap.delete("f")
        self.assertEqual(del_item.item_id, "f")
        self.assertEqual(self.heap.peek_min().item_id, "a")

        # Delete max (e: 50)
        del_item2 = self.heap.delete("e")
        self.assertEqual(del_item2.item_id, "e")
        self.assertEqual(self.heap.peek_max().item_id, "d")

        # Delete interior node (c: 30)
        self.heap.delete("c")
        self.assertNotIn("c", self.heap)

        # Non-existent delete
        with self.assertRaises(ItemNotFoundError):
            self.heap.delete("non_existent")

        remaining = []
        while not self.heap.is_empty():
            remaining.append(self.heap.extract_min().item_id)
        self.assertEqual(remaining, ["a", "b", "d"])

    def test_arbitrary_update(self):
        self.heap.insert("a", 50.0)
        self.heap.insert("b", 60.0)
        self.heap.insert("c", 70.0)

        # Update 'c' to lowest priority (5.0) -> should become peek_min
        self.heap.update("c", new_priority=5.0)
        self.assertEqual(self.heap.peek_min().item_id, "c")

        # Update 'a' to highest priority (100.0) -> should become peek_max
        self.heap.update("a", new_priority=100.0)
        self.assertEqual(self.heap.peek_max().item_id, "a")

        # Non-existent update
        with self.assertRaises(ItemNotFoundError):
            self.heap.update("unknown", new_priority=1.0)


if __name__ == "__main__":
    unittest.main()
