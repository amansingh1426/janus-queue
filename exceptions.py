"""Custom exceptions for Persistent Priority Queue."""


class PriorityQueueError(Exception):
    """Base exception for all priority queue errors."""
    pass


class EmptyQueueError(PriorityQueueError):
    """Raised when attempting to peek or extract from an empty queue."""
    pass


class ItemNotFoundError(PriorityQueueError, KeyError):
    """Raised when an operation references a non-existent item ID."""
    pass


class DuplicateItemError(PriorityQueueError, ValueError):
    """Raised when attempting to insert an item with an ID that already exists."""
    pass


class StorageError(PriorityQueueError):
    """Raised when a storage persistence operation fails."""
    pass
