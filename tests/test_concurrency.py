"""Concurrency and thread-safety tests for PersistentPriorityQueue."""

import os
import shutil
import tempfile
import threading
import unittest

from module import PersistentPriorityQueue


class TestConcurrency(unittest.TestCase):
    def setUp(self):
        self.test_dir = tempfile.mkdtemp()

    def tearDown(self):
        if os.path.exists(self.test_dir):
            shutil.rmtree(self.test_dir)

    def test_concurrent_producers_and_consumers(self):
        pq = PersistentPriorityQueue(storage_dir=self.test_dir, queue_name="concurrent_test")
        num_producers = 4
        num_consumers = 2
        items_per_producer = 50

        inserted_count = 0
        extracted_items = []
        lock = threading.Lock()

        def producer_worker(producer_id: int):
            for i in range(items_per_producer):
                item_id = f"p{producer_id}_item_{i}"
                priority = float(i % 10)
                pq.insert(item_id=item_id, priority=priority)

        def consumer_worker():
            while True:
                try:
                    item = pq.extract_min()
                    with lock:
                        extracted_items.append(item)
                except Exception:
                    # Queue might be momentarily empty
                    pass
                with lock:
                    if len(extracted_items) >= (num_producers * items_per_producer):
                        break

        threads = []
        for p in range(num_producers):
            t = threading.Thread(target=producer_worker, args=(p,))
            threads.append(t)
            t.start()

        for _ in range(num_consumers):
            t = threading.Thread(target=consumer_worker)
            threads.append(t)
            t.start()

        # Wait for all producers to finish
        for t in threads[:num_producers]:
            t.join()

        # Wait for consumers to drain remaining items
        for t in threads[num_producers:]:
            t.join(timeout=3.0)

        # Drain any remainder
        while not pq.is_empty():
            extracted_items.append(pq.extract_min())

        pq.close()

        total_expected = num_producers * items_per_producer
        self.assertEqual(len(extracted_items), total_expected)


if __name__ == "__main__":
    unittest.main()
