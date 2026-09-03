from __future__ import annotations
import http.server
import json
import os
import sys
import traceback
import urllib.parse
from typing import Any, Dict

# Ensure project root is in python module path
root_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if root_dir not in sys.path:
    sys.path.insert(0, root_dir)

from exceptions import (
    DuplicateItemError,
    EmptyQueueError,
    ItemNotFoundError,
    PriorityQueueError,
)
from app import QueueManager

# Determine writable storage directory for Vercel serverless environment
storage_dir = os.getenv("PQ_STORAGE_DIR")
if not storage_dir:
    if os.getenv("VERCEL") or not os.access(".", os.W_OK):
        storage_dir = "/tmp/pq_data"
    else:
        storage_dir = "./pq_data"

manager = QueueManager(storage_dir=storage_dir, queue_name="vercel_queue")


class handler(http.server.BaseHTTPRequestHandler):
    """Vercel Serverless HTTP Handler for JanusQueue API with robust action extraction."""

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
        if not body_bytes:
            return {}
        return json.loads(body_bytes.decode("utf-8"))

    def _extract_action(self) -> str:
        """Extract the intended API action from request URI, headers, or query parameters."""
        raw_sources = [
            self.path or "",
            self.headers.get("x-forwarded-uri", ""),
            self.headers.get("x-matched-path", ""),
            self.headers.get("x-original-uri", ""),
        ]
        combined = " ".join(raw_sources).lower()

        # Check for specific API actions in order of specificity
        actions = [
            "extract_min",
            "extract_max",
            "crash_reload",
            "checkpoint",
            "scenario",
            "insert",
            "update",
            "delete",
            "clear",
            "state",
        ]
        for act in actions:
            if act in combined:
                return act

        return "state"

    def do_OPTIONS(self) -> None:
        self.send_response(200)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    def do_GET(self) -> None:
        action = self._extract_action()
        if action == "state":
            try:
                state = manager.get_state()
                self._send_json(state)
            except Exception as e:
                self._send_json({"error": str(e), "trace": traceback.format_exc()}, status=500)
        else:
            self._send_json({"error": f"Invalid GET action: {action}"}, status=400)

    def do_POST(self) -> None:
        action = self._extract_action()

        try:
            body = self._read_json_body()

            if action == "insert":
                item_id = body.get("item_id")
                if item_id == "":
                    item_id = None
                priority = float(body.get("priority", 0.0))
                data = body.get("data", None)
                result = manager.insert(item_id, priority, data)
                self._send_json({"status": "success", "item": result, "state": manager.get_state()})

            elif action == "extract_min":
                result = manager.extract_min()
                self._send_json({"status": "success", "extracted": result, "state": manager.get_state()})

            elif action == "extract_max":
                result = manager.extract_max()
                self._send_json({"status": "success", "extracted": result, "state": manager.get_state()})

            elif action == "update":
                item_id = str(body["item_id"])
                new_priority = float(body["new_priority"]) if "new_priority" in body and body["new_priority"] is not None else None
                new_data = body.get("new_data", None)
                result = manager.update(item_id, new_priority, new_data)
                self._send_json({"status": "success", "item": result, "state": manager.get_state()})

            elif action == "delete":
                item_id = str(body["item_id"])
                result = manager.delete(item_id)
                self._send_json({"status": "success", "deleted": result, "state": manager.get_state()})

            elif action == "clear":
                manager.clear()
                self._send_json({"status": "success", "state": manager.get_state()})

            elif action == "checkpoint":
                manager.checkpoint()
                self._send_json({"status": "success", "message": "Snapshot saved and WAL compacted!", "state": manager.get_state()})

            elif action == "crash_reload":
                res = manager.crash_and_reload()
                self._send_json({"status": "success", "result": res, "state": manager.get_state()})

            elif action == "scenario":
                scenario = body.get("scenario", "hospital_triage")
                res = manager.load_scenario(scenario)
                self._send_json({"status": "success", "result": res, "state": manager.get_state()})

            else:
                self._send_json({"error": f"Action '{action}' not recognized"}, status=400)

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
