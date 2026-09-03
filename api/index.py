from __future__ import annotations
import os
import sys

# Ensure parent directory is in python module search path
parent_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if parent_dir not in sys.path:
    sys.path.insert(0, parent_dir)

from app import AppRequestHandler, QueueManager

# Determine writable storage directory (Vercel serverless read-only filesystem uses /tmp)
storage_dir = os.getenv("PQ_STORAGE_DIR")
if not storage_dir:
    if os.getenv("VERCEL") or not os.access(".", os.W_OK):
        storage_dir = "/tmp/pq_data"
    else:
        storage_dir = "./pq_data"

# Initialize global QueueManager singleton for serverless context
manager = QueueManager(storage_dir=storage_dir, queue_name="vercel_queue")
AppRequestHandler.manager = manager

# Vercel @vercel/python entry point
class handler(AppRequestHandler):
    """Serverless HTTP Handler for Vercel deployment."""
    pass
