import os
import subprocess
import sys
import pytest
from peewee import OperationalError
from local_notes import Store, StoreError


def test_connection(tmp_path):
    s = Store(tmp_path / 'a.db')
    assert s.db.is_closed()
    with s:
        assert s.db.execute_sql('PRAGMA foreign_keys').fetchone() == (1,)
        assert s.db.execute_sql('PRAGMA busy_timeout').fetchone() == (5000,)
        with pytest.raises(StoreError):
            s.__enter__()
    assert s.db.is_closed()
    with pytest.raises(StoreError):
        s._check()


def test_exception_cleanup(tmp_path):
    s = Store(tmp_path / 'a.db')
    with pytest.raises(ValueError), s:
        raise ValueError('test')
    assert s.db.is_closed()


def test_bindings(tmp_path):
    with Store(tmp_path / 'a.db') as a, Store(tmp_path / 'b.db') as b:
        assert a.Notebook._meta.database is a.db
        assert b.Notebook._meta.database is b.db
        assert a.Notebook is not b.Notebook


def test_invalid_path(tmp_path):
    s = Store(tmp_path / 'missing' / 'db')
    with pytest.raises(OperationalError):
        with s:
            pass
    assert not (tmp_path / 'missing').exists()
    assert s.db.is_closed()
    with pytest.raises(ValueError):
        Store(':memory:')


def test_import_no_io(tmp_path):
    root = os.getcwd()
    env = dict(os.environ, PYTHONPATH=root)
    subprocess.run([sys.executable, '-c', 'import local_notes; import local_notes.models'],
                   cwd=tmp_path, env=env, check=True)
    assert list(tmp_path.iterdir()) == []
