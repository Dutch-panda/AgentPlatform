import ast
from pathlib import Path
import pytest
from peewee import OperationalError, IntegrityError
from local_notes import Store, StoreError


def test_visibility_and_connections(tmp_path):
    path = tmp_path / 'db'
    with Store(path) as writer:
        writer.initialize()
        with Store(path) as reader:
            reader.require_schema()
            assert reader.db.execute_sql('PRAGMA foreign_keys').fetchone() == (1,)
            assert writer.db.execute_sql('PRAGMA foreign_keys').fetchone() == (1,)
            with writer.transaction():
                writer.create_notebook('pending')
                assert reader.list_notebooks() == []
            assert [n.name for n in reader.list_notebooks()] == ['pending']
            with pytest.raises(IntegrityError):
                reader.create_note(999, 'invalid')
    with Store(path) as reopened:
        reopened.require_schema()
        assert len(reopened.list_notebooks()) == 1


def test_contention(tmp_path):
    path = tmp_path / 'db'
    with Store(path) as a:
        a.initialize()
        with Store(path) as b:
            b.db.execute_sql('PRAGMA busy_timeout=1')
            try:
                with a.transaction():
                    a.create_notebook('held')
                    with pytest.raises(OperationalError, match='locked'):
                        b.create_notebook('blocked')
            finally:
                b.db.execute_sql('PRAGMA busy_timeout=5000')
            assert b.db.execute_sql('PRAGMA busy_timeout').fetchone() == (5000,)
            assert [n.name for n in b.list_notebooks()] == ['held']


def test_isolated_files(tmp_path):
    for name in ['a', 'b']:
        with Store(tmp_path / name) as s:
            s.initialize()
            assert s.list_notebooks() == []
            s.create_notebook(name)


def test_installed_code_no_network_imports():
    banned = {'socket', 'urllib', 'requests', 'http', 'httpx', 'aiohttp'}
    for root in ['local_notes', 'tests']:
        for path in Path(root).glob('*.py'):
            tree = ast.parse(path.read_text())
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    assert not ({n.name.split('.')[0] for n in node.names} & banned)
                elif isinstance(node, ast.ImportFrom):
                    assert (node.module or '').split('.')[0] not in banned
