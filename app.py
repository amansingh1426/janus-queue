#!/usr/bin/env python3
"""Interactive Web Server for Persistent Priority Queue.

Provides a full REST API and serves the modern GUI dashboard
using Python standard library with zero external dependencies.
"""

from __future__ import annotations
import argparse
import http.server
import json
import math
import os
import socketserver
import sys
import threading
import traceback
import urllib.parse
from typing import Any, Dict, List, Optional

from exceptions import (
    DuplicateItemError,
    EmptyQueueError,
    ItemNotFoundError,
    PriorityQueueError,
)
from module import PersistentPriorityQueue
from min_max_heap import QueueItem


class QueueManager:
    """Manages the lifecycle, operations, and WAL inspection of PersistentPriorityQueue."""

    def __init__(self, storage_dir: str = "./pq_data", queue_name: str = "web_queue") -> None:
        self.storage_dir = os.path.abspath(storage_dir)
        self.queue_name = queue_name
        self._lock = threading.Lock()
        self.pq: PersistentPriorityQueue = PersistentPriorityQueue(
            storage_dir=self.storage_dir,
            queue_name=self.queue_name,
            sync_on_write=True,
        )
        self.total_inserts = 0
        self.total_extractions = 0
        self.total_updates = 0
        self.total_deletions = 0
        self.crash_recoveries_count = 0

    def get_state(self) -> Dict[str, Any]:
        with self._lock:
            heap_items: List[QueueItem] = self.pq._heap.get_all_items()
            n = len(heap_items)
            nodes = []
            for idx, item in enumerate(heap_items):
                level = int(math.floor(math.log2(idx + 1))) if idx >= 0 else 0
                is_min = (level % 2 == 0)
                parent = (idx - 1) // 2 if idx > 0 else None
                left = 2 * idx + 1 if (2 * idx + 1) < n else None
                right = 2 * idx + 2 if (2 * idx + 2) < n else None
                nodes.append({
                    "item_id": item.item_id,
                    "priority": item.priority,
                    "seq": item.seq,
                    "data": item.data,
                    "index": idx,
                    "level": level,
                    "is_min_level": is_min,
                    "parent": parent,
                    "left_child": left,
                    "right_child": right,
                })

            peek_min = None
            peek_max = None
            if not self.pq.is_empty():
                try:
                    peek_min = self.pq.peek_min().to_dict()
                except Exception:
                    pass
                try:
                    peek_max = self.pq.peek_max().to_dict()
                except Exception:
                    pass

            wal_records = self._read_wal_entries(limit=40)
            snapshot_info = self._get_snapshot_info()

            return {
                "queue_name": self.queue_name,
                "storage_dir": self.storage_dir,
                "is_empty": self.pq.is_empty(),
                "size": len(self.pq),
                "nodes": nodes,
                "peek_min": peek_min,
                "peek_max": peek_max,
                "wal_records": wal_records,
                "snapshot_info": snapshot_info,
                "stats": {
                    "total_inserts": self.total_inserts,
                    "total_extractions": self.total_extractions,
                    "total_updates": self.total_updates,
                    "total_deletions": self.total_deletions,
                    "crash_recoveries": self.crash_recoveries_count,
                },
            }

    def _read_wal_entries(self, limit: int = 40) -> List[Dict[str, Any]]:
        wal_path = os.path.join(self.storage_dir, f"{self.queue_name}.wal")
        if not os.path.exists(wal_path):
            return []
        try:
            with open(wal_path, "r", encoding="utf-8") as f:
                lines = f.readlines()
            records = []
            for line_idx, line in enumerate(reversed(lines[-limit:])):
                line_str = line.strip()
                if not line_str:
                    continue
                parts = line_str.split(" ", 1)
                checksum = parts[0] if len(parts) > 0 else ""
                json_data = parts[1] if len(parts) > 1 else "{}"
                try:
                    parsed = json.loads(json_data)
                    records.append({
                        "line_num": len(lines) - line_idx,
                        "checksum": checksum,
                        "op": parsed.get("op", "UNKNOWN"),
                        "payload": parsed.get("payload", {}),
                        "raw": line_str,
                        "valid": True,
                    })
                except Exception:
                    records.append({
                        "line_num": len(lines) - line_idx,
                        "checksum": checksum,
                        "op": "CORRUPTED",
                        "payload": {},
                        "raw": line_str,
                        "valid": False,
                    })
            return records
        except Exception:
            return []

    def _get_snapshot_info(self) -> Dict[str, Any]:
        snap_path = os.path.join(self.storage_dir, f"{self.queue_name}.snapshot.json")
        if not os.path.exists(snap_path):
            return {"exists": False, "item_count": 0, "size_bytes": 0}
        try:
            stat = os.stat(snap_path)
            with open(snap_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            return {
                "exists": True,
                "item_count": len(data.get("items", [])),
                "seq_counter": data.get("seq_counter", 0),
                "size_bytes": stat.st_size,
            }
        except Exception:
            return {"exists": True, "item_count": 0, "size_bytes": 0}

    def insert(self, item_id: Optional[str], priority: float, data: Any = None) -> Dict[str, Any]:
        with self._lock:
            item = self.pq.insert(item_id=item_id, priority=priority, data=data)
            self.total_inserts += 1
            return item.to_dict()

    def extract_min(self) -> Dict[str, Any]:
        with self._lock:
            item = self.pq.extract_min()
            self.total_extractions += 1
            return item.to_dict()

    def extract_max(self) -> Dict[str, Any]:
        with self._lock:
            item = self.pq.extract_max()
            self.total_extractions += 1
            return item.to_dict()

    def update(self, item_id: str, new_priority: Optional[float] = None, new_data: Any = None) -> Dict[str, Any]:
        with self._lock:
            item = self.pq.update(item_id=item_id, new_priority=new_priority, new_data=new_data)
            self.total_updates += 1
            return item.to_dict()

    def delete(self, item_id: str) -> Dict[str, Any]:
        with self._lock:
            item = self.pq.delete(item_id=item_id)
            self.total_deletions += 1
            return item.to_dict()

    def clear(self) -> None:
        with self._lock:
            self.pq.clear()

    def checkpoint(self) -> None:
        with self._lock:
            self.pq.checkpoint()

    def crash_and_reload(self) -> Dict[str, Any]:
        """Simulate a sudden crash by dropping the in-memory object and reloading from disk."""
        with self._lock:
            try:
                self.pq.storage.close()
            except Exception:
                pass
            self.pq = PersistentPriorityQueue(
                storage_dir=self.storage_dir,
                queue_name=self.queue_name,
                sync_on_write=True,
            )
            self.crash_recoveries_count += 1
            return {
                "status": "success",
                "recovered_items_count": len(self.pq),
                "message": f"Successfully reloaded queue '{self.queue_name}' with {len(self.pq)} items from disk WAL!",
            }

    def load_scenario(self, scenario_name: str) -> Dict[str, Any]:
        with self._lock:
            self.pq.clear()
            if scenario_name == "hospital_triage":
                patients = [
                    ("P_001", 1.0, {"name": "Robert Taylor", "acuity": "Resuscitation (Level 1)", "condition": "Acute chest pain & cardiac arrest"}),
                    ("P_002", 2.0, {"name": "Emily Clark", "acuity": "Emergent (Level 2)", "condition": "Severe compound fracture"}),
                    ("P_003", 3.0, {"name": "John Doe", "acuity": "Urgent (Level 3)", "condition": "Severe abdominal pain & fever"}),
                    ("P_004", 4.0, {"name": "Sarah Miller", "acuity": "Less Urgent (Level 4)", "condition": "Sprained wrist and mild contusion"}),
                    ("P_005", 5.0, {"name": "Jane Smith", "acuity": "Non-urgent (Level 5)", "condition": "Routine prescription refill"}),
                    ("P_006", 1.5, {"name": "Michael Chang", "acuity": "Emergent (Level 2)", "condition": "Suspected stroke symptoms"}),
                    ("P_007", 3.5, {"name": "Olivia Davis", "acuity": "Urgent (Level 3)", "condition": "Deep laceration requiring sutures"}),
                ]
                for p_id, prio, data in patients:
                    self.pq.insert(p_id, prio, data)
                return {"message": f"Loaded Hospital ER Triage scenario ({len(patients)} patients admitted)."}

            elif scenario_name == "cloud_scheduler":
                jobs = [
                    ("job_sys_alert", 0.5, {"type": "CRITICAL", "description": "DDoS Mitigation Route Update", "owner": "SecurityBot"}),
                    ("job_auth_req", 1.0, {"type": "API_HIGH", "description": "OAuth Token Verification Batch", "owner": "AuthService"}),
                    ("job_db_wal_flush", 1.2, {"type": "SYSTEM", "description": "Database WAL Page Sync", "owner": "PostgresDB"}),
                    ("job_payment_tx", 2.0, {"type": "TRANSACTION", "description": "Stripe Payout Webhook", "owner": "BillingWorker"}),
                    ("job_ml_inference", 15.0, {"type": "BATCH_AI", "description": "LLM Embeddings Generation", "owner": "AI_Cluster"}),
                    ("job_email_blast", 40.0, {"type": "MARKETING", "description": "Weekly Newsletter", "owner": "MarketingApp"}),
                    ("job_log_rotate", 95.0, {"type": "MAINTENANCE", "description": "Compress log archives", "owner": "CronDaemon"}),
                ]
                for j_id, prio, data in jobs:
                    self.pq.insert(j_id, prio, data)
                return {"message": f"Loaded Cloud Task Scheduler scenario ({len(jobs)} jobs queued)."}

            elif scenario_name == "tie_breaker_demo":
                items = [
                    ("alpha_1", 10.0, {"note": "Inserted 1st with priority 10"}),
                    ("alpha_2", 10.0, {"note": "Inserted 2nd with priority 10"}),
                    ("alpha_3", 10.0, {"note": "Inserted 3rd with priority 10"}),
                    ("alpha_4", 10.0, {"note": "Inserted 4th with priority 10"}),
                    ("prio_high", 2.0, {"note": "Higher priority (extracted first)"}),
                    ("prio_low", 50.0, {"note": "Lowest priority (extracted last)"}),
                ]
                for i_id, prio, data in items:
                    self.pq.insert(i_id, prio, data)
                return {"message": f"Loaded FIFO Sequence Tie-Breaker scenario ({len(items)} items with duplicate priorities)."}

            else:
                return {"message": "Unknown scenario"}


class AppRequestHandler(http.server.SimpleHTTPRequestHandler):
    """Custom HTTP Request Handler serving web assets and REST API."""

    manager: QueueManager

    def __init__(self, *args, **kwargs) -> None:
        web_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "web")
        super().__init__(*args, directory=web_dir, **kwargs)

    def _send_json(self, data: Any, status: int = 200) -> None:
        response_bytes = json.dumps(data).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(response_bytes)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.send_header("Cache-Control", "no-cache, no-store, must-revalidate")
        self.end_headers()
        self.wfile.write(response_bytes)

    def _read_json_body(self) -> Dict[str, Any]:
        content_len = int(self.headers.get("Content-Length", 0))
        if content_len == 0:
            return {}
        body_bytes = self.rfile.read(content_len)
        return json.loads(body_bytes.decode("utf-8"))

    def do_OPTIONS(self) -> None:
        self.send_response(200)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    def do_GET(self) -> None:
        parsed_url = urllib.parse.urlparse(self.path)
        path = parsed_url.path

        if path == "/api/state":
            try:
                state = self.manager.get_state()
                self._send_json(state)
            except Exception as e:
                self._send_json({"error": str(e), "trace": traceback.format_exc()}, status=500)
        elif path == "/" or path == "":
            self.path = "/index.html"
            super().do_GET()
        else:
            super().do_GET()

    def do_POST(self) -> None:
        parsed_url = urllib.parse.urlparse(self.path)
        path = parsed_url.path

        try:
            body = self._read_json_body()

            if path == "/api/insert":
                item_id = body.get("item_id")
                if item_id == "":
                    item_id = None
                priority = float(body.get("priority", 0.0))
                data = body.get("data", None)
                result = self.manager.insert(item_id, priority, data)
                self._send_json({"status": "success", "item": result, "state": self.manager.get_state()})

            elif path == "/api/extract_min":
                result = self.manager.extract_min()
                self._send_json({"status": "success", "extracted": result, "state": self.manager.get_state()})

            elif path == "/api/extract_max":
                result = self.manager.extract_max()
                self._send_json({"status": "success", "extracted": result, "state": self.manager.get_state()})

            elif path == "/api/update":
                item_id = str(body["item_id"])
                new_priority = float(body["new_priority"]) if "new_priority" in body and body["new_priority"] is not None else None
                new_data = body.get("new_data", None)
                result = self.manager.update(item_id, new_priority, new_data)
                self._send_json({"status": "success", "item": result, "state": self.manager.get_state()})

            elif path == "/api/delete":
                item_id = str(body["item_id"])
                result = self.manager.delete(item_id)
                self._send_json({"status": "success", "deleted": result, "state": self.manager.get_state()})

            elif path == "/api/clear":
                self.manager.clear()
                self._send_json({"status": "success", "state": self.manager.get_state()})

            elif path == "/api/checkpoint":
                self.manager.checkpoint()
                self._send_json({"status": "success", "message": "Snapshot saved and WAL compacted!", "state": self.manager.get_state()})

            elif path == "/api/crash_reload":
                res = self.manager.crash_and_reload()
                self._send_json({"status": "success", "result": res, "state": self.manager.get_state()})

            elif path == "/api/scenario":
                scenario = body.get("scenario", "hospital_triage")
                res = self.manager.load_scenario(scenario)
                self._send_json({"status": "success", "result": res, "state": self.manager.get_state()})

            else:
                self._send_json({"error": f"Endpoint '{path}' not found"}, status=404)

        except DuplicateItemError as e:
            self._send_json({"error": str(e), "code": "DUPLICATE_ITEM"}, status=400)
        except EmptyQueueError as e:
            self._send_json({"error": str(e), "code": "EMPTY_QUEUE"}, status=400)
        except ItemNotFoundError as e:
            self._send_json({"error": str(e), "code": "ITEM_NOT_FOUND"}, status=404)
        except ValueError as e:
            self._send_json({"error": f"Validation Error: {str(e)}", "code": "INVALID_VALUE"}, status=400)
        except Exception as e:
            self._send_json({"error": str(e), "trace": traceback.format_exc()}, status=500)


def run_server(port: int = 8000, storage_dir: str = "./pq_data") -> None:
    manager = QueueManager(storage_dir=storage_dir, queue_name="interactive_queue")
    AppRequestHandler.manager = manager

    class ThreadingServer(socketserver.ThreadingMixIn, http.server.HTTPServer):
        daemon_threads = True

    server_address = ("", port)
    with ThreadingServer(server_address, AppRequestHandler) as httpd:
        print("=" * 65)
        print("  🌟 Persistent Priority Queue - Interactive Web Interface")
        print("=" * 65)
        print(f"  -> Local URL:     http://localhost:{port}")
        print(f"  -> Data Storage:  {os.path.abspath(storage_dir)}")
        print(f"  -> Press Ctrl+C in terminal to stop server")
        print("=" * 65)
        sys.stdout.flush()
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            print("\nShutting down server...")
            manager.pq.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Persistent Priority Queue Web Server")
    parser.add_argument("--port", type=int, default=8000, help="Port to run the HTTP server on (default: 8000)")
    parser.add_argument("--storage-dir", type=str, default="./pq_data", help="Directory for WAL & snapshot storage")
    args = parser.parse_args()

    run_server(port=args.port, storage_dir=args.storage_dir)
