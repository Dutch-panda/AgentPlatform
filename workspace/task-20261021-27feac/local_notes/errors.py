class StoreError(Exception):
    """Invalid lifecycle or schema state."""


class SchemaError(StoreError):
    pass


class NotFoundError(StoreError):
    pass
