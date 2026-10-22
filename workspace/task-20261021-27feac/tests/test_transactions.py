import pytest
from peewee import IntegrityError


def test_outer_rollback(store):
    with pytest.raises(RuntimeError), store.transaction():
        n = store.create_notebook('a')
        store.create_note(n.id,'x')
        raise RuntimeError('abort')
    assert store.list_notebooks() == []
    assert store.list_notes(1) == []


def test_nested_savepoint(store):
    with store.transaction():
        a = store.create_notebook('a')
        with pytest.raises(IntegrityError):
            store.create_notebook('a')
        store.create_note(a.id,'ok')
    assert len(store.list_notes(a.id)) == 1
    assert store.db.transaction_depth() == 0
    store.list_notebooks()
    assert store.db.transaction_depth() == 0
