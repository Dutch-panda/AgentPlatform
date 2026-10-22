"""Offline illustrative notes; importing performs no I/O."""
from .store import Store
from .errors import StoreError, SchemaError, NotFoundError

__all__ = ['Store', 'StoreError', 'SchemaError', 'NotFoundError']
