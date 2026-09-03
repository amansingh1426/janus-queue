# JanusQueue

A production-grade, thread-safe **Durable Double-Ended Priority Queue (DEPQ)** featuring persistence via an append-only **Write-Ahead Log (WAL)** with atomic snapshotting and crash recovery, as well as an optional **PostgreSQL** relational persistence engine.

---

## Table of Contents
1. [Overview & Assignment Checklist](#1-overview--assignment-checklist)
2. [Data Structure & Architecture](#2-data-structure--architecture)
   - [Min-Max Heap Invariants](#min-max-heap-invariants)
   - [Position Index Map for $O(\log N)$ Mutations](#position-index-map-for-olog-n-mutations)
3. [Durable Persistence Model](#3-durable-persistence-model)
   - [Write-Ahead Log (WAL) & Crash Recovery](#write-ahead-log-wal--crash-recovery)
   - [Snapshot Compaction](#snapshot-compaction)
   - [Relational Storage (PostgreSQL)](#relational-storage-postgresql)
4. [Time and Space Complexity](#4-time-and-space-complexity)
5. [Supported Operations & API](#5-supported-operations--api)
6. [Real-World Use Cases](#6-real-world-use-cases)
7. [Getting Started & Running Tests](#7-getting-started--running-tests)
8. [Interview Discussion Guide](#8-interview-discussion-guide)

---

## 1. Overview & Assignment Checklist

This repository implements all requirements outlined in the **Persistent Priority Queue** assignment specification:

| Requirement | Implementation Details | Status |
| :--- | :--- | :--- |
| **`insert(item_id, priority, data)`** | Inserts element with $O(\log N)$ heap push-up and WAL append | ✅ Complete |
| **`extract_min()`** | Extracts element with smallest priority in $O(\log N)$ time | ✅ Complete |
| **`extract_max()`** | Extracts element with largest priority in $O(\log N)$ time | ✅ Complete |
| **`peek(mode='min'/'max')`** | Inspects min or max element in $O(1)$ time without removal | ✅ Complete |
| **`update(item_id, priority, data)`** | Updates item priority/payload and rebalances in $O(\log N)$ time | ✅ Complete |
| **`delete(item_id)`** | Deletes arbitrary item by ID in $O(\log N)$ time | ✅ Complete |
| **`is_empty()`** | Returns `True` if queue contains 0 items in $O(1)$ time | ✅ Complete |
| **File Persistence** | Append-only WAL with CRC32 checksums & atomic snapshotting | ✅ Complete |
| **PostgreSQL Persistence** | Pluggable relational database adapter | ✅ Complete |
| **Main Submission File** | Primary module placed in `module.py` | ✅ Complete |
| **Tests & Verification** | 30 automated test cases covering edge cases & concurrency | ✅ Complete |

---

## 2. Data Structure & Architecture

```
+-------------------------------------------------------------------------------+
|                           PersistentPriorityQueue                             |
|       (Exposes: insert, extract_min, extract_max, peek, update, delete)       |
+---------------------------------------+---------------------------------------+
                                        |
                 +----------------------+----------------------+
                 |                                             |
                 v                                             v
   +---------------------------+                 +---------------------------+
   |        MinMaxHeap         |                 |       StorageEngine       |
   | (In-Memory DEPQ Core)     |                 |   (Durable Persistence)   |
   | - Array-backed tree       |                 +-------------+-------------+
   | - Alternating Min/Max tier|                               |
   | - Dict[item_id -> index]  |                 +-------------+-------------+
   +---------------------------+                 |                           |
                                                 v                           v
                                       +-------------------+       +-------------------+
                                       |  FileWALStorage   |       |  PostgresStorage  |
                                       | (WAL + Snapshot)  |       |   (Relational)    |
                                       +-------------------+       +-------------------+
```

### Min-Max Heap Invariants
A standard binary heap only supports efficient extraction from one end ($O(1)$ peek min, but $O(N)$ to find max). To support both `extract_min` and `extract_max` efficiently, this implementation uses a **Min-Max Heap**:
- A complete binary tree stored in a contiguous array where levels alternate between **Min levels** and **Max levels**.
  - **Level 0 (Root)**: Min level (holds global minimum element).
  - **Level 1**: Max level (holds global maximum elements in children).
  - **Level 2**: Min level.
  - **Level 3**: Max level.
- **Invariant**:
  - For any node $x$ on a **Min level**, $x$ is smaller than or equal to all nodes in the subtree rooted at $x$.
  - For any node $y$ on a **Max level**, $y$ is greater than or equal to all nodes in the subtree rooted at $y$.

### Position Index Map for $O(\log N)$ Mutations
Standard binary heaps require $O(N)$ linear scans to locate an arbitrary element for `update()` or `delete()`. 
- We maintain an auxiliary hash map: `_pos_map: Dict[str, int]` mapping each unique `item_id` to its current index in the heap array.
- Every internal element swap updates `_pos_map` in $O(1)$.
- As a result, looking up an item takes $O(1)$ and rebalancing after modification takes $O(\log N)$, yielding **$O(\log N)$ total time for arbitrary updates and deletions**.

### Deterministic FIFO Tie-Breaking
When two items are inserted with identical priority values, an internal monotonic sequence counter (`seq`) breaks ties, guaranteeing stable **First-In, First-Out (FIFO)** order.

---

## 3. Durable Persistence Model

### Write-Ahead Log (WAL) & Crash Recovery
1. **Append-Only Journal**: Every mutating operation (`INSERT`, `UPDATE`, `DELETE`, `EXTRACT_MIN`, `EXTRACT_MAX`, `CLEAR`) is serialized to an append-only `.wal` file before the in-memory mutation completes.
2. **CRC32 Checksums**: Each line in the WAL is prefixed with an 8-character hexadecimal CRC32 checksum:
   ```
   d41d8cd9 {"op":"INSERT","payload":{"item_id":"task_1","priority":1.0,"seq":1,"data":{}}}
   ```
3. **Crash Resilience**: If a sudden power cut or process termination occurs during a write, incomplete trailing lines fail the CRC32 verification and are safely skipped during replay, preventing corruption.
4. **Fsync Durability**: File writes call `os.fsync()` to ensure dirty OS page cache buffers are committed to non-volatile storage.

### Snapshot Compaction
To prevent the WAL log from growing indefinitely:
- Every $K$ operations (configurable via `auto_checkpoint_interval`), the queue performs an atomic checkpoint.
- The entire heap state is written to a temporary snapshot file and atomically swapped using `os.replace()`.
- The active `.wal` file is then safely truncated to 0 bytes.

### Relational Storage (PostgreSQL)
For multi-process or enterprise deployments, `PostgresStorage` stores items in a PostgreSQL table with composite indexing on `(priority ASC, seq ASC)`:
```sql
CREATE TABLE IF NOT EXISTS persistent_priority_queue (
    item_id VARCHAR(255) PRIMARY KEY,
    priority DOUBLE PRECISION NOT NULL,
    seq BIGINT NOT NULL,
    data JSONB
);
CREATE INDEX idx_pq_priority ON persistent_priority_queue (priority ASC, seq ASC);
```

---

## 4. Time and Space Complexity

| Operation | In-Memory Min-Max Heap | Persistence Overhead (WAL) | Overall Time Complexity | Space Complexity |
| :--- | :--- | :--- | :--- | :--- |
| **`peek_min()` / `peek()`** | $O(1)$ | None (in-memory read) | **$O(1)$** | $O(1)$ |
| **`peek_max()`** | $O(1)$ | None (in-memory read) | **$O(1)$** | $O(1)$ |
| **`insert(id, prio, data)`**| $O(\log N)$ | $O(1)$ sequential append | **$O(\log N)$** | $O(1)$ |
| **`extract_min()`** | $O(\log N)$ | $O(1)$ sequential append | **$O(\log N)$** | $O(1)$ |
| **`extract_max()`** | $O(\log N)$ | $O(1)$ sequential append | **$O(\log N)$** | $O(1)$ |
| **`update(id, prio)`** | $O(\log N)$ ($O(1)$ lookup via map) | $O(1)$ sequential append | **$O(\log N)$** | $O(1)$ |
| **`delete(id)`** | $O(\log N)$ ($O(1)$ lookup via map) | $O(1)$ sequential append | **$O(\log N)$** | $O(1)$ |
| **`is_empty()`** | $O(1)$ | None | **$O(1)$** | $O(1)$ |
| **Total Memory / Disk** | $O(N)$ | $O(N)$ bounded by snapshots | — | **$O(N)$** |

---

## 5. Supported Operations & API

### Code Example
```python
from module import PersistentPriorityQueue

# Initialize persistent queue (recovers previous state if exists)
with PersistentPriorityQueue(storage_dir="./my_queue_data", queue_name="tasks") as pq:
    # 1. Insert items (with custom ID, priority, and payload)
    pq.insert(item_id="task_urgent", priority=1.0, data={"desc": "Security patch"})
    pq.insert(item_id="task_bg", priority=50.0, data={"desc": "Log cleanup"})
    pq.insert(item_id="task_normal", priority=10.0, data={"desc": "Send invoice"})

    # 2. Check emptiness and size
    print(pq.is_empty())  # False
    print(len(pq))        # 3

    # 3. Peek top elements
    print(pq.peek_min().item_id)  # 'task_urgent'
    print(pq.peek_max().item_id)  # 'task_bg'

    # 4. Update priority or payload
    pq.update(item_id="task_bg", new_priority=0.5)  # Promoted to highest priority!
    print(pq.peek_min().item_id)  # 'task_bg'

    # 5. Delete specific item
    pq.delete("task_normal")

    # 6. Extract min and max
    top_task = pq.extract_min()  # 'task_bg' (priority 0.5)
    last_task = pq.extract_max() # 'task_urgent' (priority 1.0)
```

---

## 6. Real-World Use Cases

### 1. Operating System & Distributed Job Scheduling
- **Context**: Schedulers (e.g., Linux CFS, Kubernetes, Celery, RabbitMQ) manage tasks with different deadlines and compute priorities.
- **Why DEPQ + Persistence?**:
  - `extract_min`: Picks the highest-priority urgent task to execute next on an available CPU core.
  - `extract_max`: Identifies lowest-priority idle tasks to throttle or preempt under resource pressure.
  - `update`: Implements **priority aging** (gradually boosting priority of long-waiting tasks to prevent starvation).
  - **Durability**: If a worker or node crashes, uncompleted jobs are recovered from the WAL without losing scheduled state.

### 2. Emergency Medical Triage (Hospital ER)
- **Context**: Emergency departments classify incoming patients according to acuity scales (e.g., ESI Level 1 = Resuscitation, Level 5 = Non-urgent).
- **Why DEPQ + Persistence?**:
  - `extract_min`: Assigns available physicians to the most critical patients first.
  - `update`: Patient symptoms often deteriorate suddenly (e.g. onset of acute anaphylaxis), requiring instant priority escalation.
  - **Durability**: Hospital medical records must never lose a patient's position in the admission triage queue during a power failure.

### 3. Network Packet Scheduling & Quality of Service (QoS)
- **Context**: Network routers prioritize low-latency traffic (VoIP, video conference packets) over bulk data transfers (file downloads).
- **Why DEPQ?**:
  - `extract_min`: Transmits real-time audio/video packets immediately.
  - `extract_max`: Under network congestion buffer overflows, drops lowest-priority bulk packets first (Active Queue Management).

### 4. Graph Algorithms & Navigation (Dijkstra’s Algorithm & A* Search)
- **Context**: Pathfinding in Google Maps, GPS routing, and robotics path planning.
- **Why DEPQ?**:
  - `extract_min`: Always explores the node with the minimum tentative distance.
  - `update` (Decrease-Key): When a shorter path to an existing graph node is discovered, its distance key is updated in $O(\log N)$.

### 5. Discrete-Event Simulation & Financial Order Books
- **Context**: Simulating complex physical systems, flight simulations, or matching financial limit orders (bid/ask prices).
- **Why DEPQ?**:
  - Double-ended access allows querying both the highest bid (max) and lowest ask (min) in $O(1)$ time.

---

## 7. Getting Started & Running Tests

### Project Structure
```
janus-queue/
├── module.py               # Main submission module (PersistentPriorityQueue)
├── min_max_heap.py         # Indexed Min-Max Heap core data structure
├── storage.py              # File-based WAL engine & PostgreSQL backend
├── exceptions.py           # Custom exception hierarchy
├── run_demo.py             # Interactive CLI demo with real-world scenarios
├── README.md               # Documentation, design choices, complexity & use cases
└── tests/
    ├── test_min_max_heap.py# 11 tests verifying Min-Max heap algorithm & invariants
    ├── test_queue_ops.py   # 12 tests verifying all 7 required operations & edge cases
    ├── test_persistence.py # 3 tests for WAL replay, crash recovery & snapshotting
    └── test_concurrency.py # Multi-threaded stress testing (race conditions)
```

### Running All Automated Tests
The test suite uses Python's standard `unittest` framework (zero external dependencies required):
```bash
python3 -m unittest discover -s tests -v
```

### Running the Web GUI Dashboard Locally
Run the interactive REST API & web dashboard (zero external dependencies):
```bash
python3 app.py --port 8000
```
Open `http://localhost:8000` in your browser.

### Deploying to Vercel
This repository is configured for serverless deployment on Vercel with Python functions and static asset CDN routing (`vercel.json` + `api/index.py`).

1. Push your repository to GitHub.
2. Import the repository into [Vercel](https://vercel.com/new).
3. Vercel will automatically build and deploy the web dashboard and REST API.

---

## 8. Interview Discussion Guide

When discussing this implementation during an interview, highlight the following key architectural decisions:

1. **Why Min-Max Heap instead of Dual Heaps?**
   - *Dual Heaps* (maintaining a Min-Heap and Max-Heap simultaneously) require duplicate references, cross-pointers, and double memory overhead ($2N$).
   - *Min-Max Heap* achieves $O(1)$ min/max peeks and $O(\log N)$ min/max extractions in a **single array** with zero pointer overhead and superior CPU cache locality.
2. **How is $O(\log N)$ arbitrary update and delete achieved?**
   - Standard heaps require an $O(N)$ linear search to find an item.
   - By indexing the heap with an in-memory hash map (`item_id -> index`) kept updated on every swap, lookup is $O(1)$, and bubble-up / trickle-down is $O(\log N)$.
3. **How does the Write-Ahead Log (WAL) guarantee durability?**
   - State mutations are written to an append-only file and flushed to disk with `os.fsync()` before modifying memory.
   - CRC32 checksums protect against torn writes or partial writes during sudden power interruptions.
   - Periodic snapshotting bounds recovery time and disk space usage.
