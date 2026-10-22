import pytest
from peewee import IntegrityError
from local_notes import Store, SchemaError
from local_notes import schema


def test_initialize_defaults_constraints(tmp_path):
    with Store(tmp_path / 'db') as s:
        s.initialize(); s.initialize()
        s.db.execute_sql("INSERT INTO notebooks(name) VALUES ('A')")
        s.db.execute_sql("INSERT INTO notebooks(name) VALUES ('a')")
        s.db.execute_sql("INSERT INTO notes(notebook_id,title) VALUES (1,'你好')")
        row = s.db.execute_sql('SELECT body,created_at,updated_at FROM notes').fetchone()
        assert row[0] == '' and row[1].endswith('Z') and row[2].endswith('Z')
        for sql in ["INSERT INTO notebooks(name) VALUES (' ')",
                    "INSERT INTO notebooks(name) VALUES (NULL)",
                    "INSERT INTO notebooks(name) VALUES ('A')",
                    "INSERT INTO notes(notebook_id,title) VALUES (99,'x')",
                    "INSERT INTO notes(notebook_id,title) VALUES (1,' ')",
                    "INSERT INTO notes(notebook_id,title) VALUES (1,NULL)",
                    "INSERT INTO notes(notebook_id,title,body) VALUES (1,'x',NULL)"]:
            with pytest.raises(IntegrityError), s.db.atomic():
                s.db.execute_sql(sql)
        assert s.db.execute_sql("PRAGMA index_info('notes_notebook_id_id')").fetchall() == [(0,1,'notebook_id'),(1,0,'id')]
        s.db.execute_sql('DELETE FROM notebooks WHERE id=1')
        assert s.db.execute_sql('SELECT count(*) FROM notes').fetchone() == (0,)


@pytest.mark.parametrize('version', [0, 2])
def test_refusal_unchanged(tmp_path, version):
    with Store(tmp_path / 'db') as s:
        s.db.execute_sql('CREATE TABLE foreign_data(value TEXT)')
        s.db.execute_sql("INSERT INTO foreign_data VALUES ('keep')")
        s.db.execute_sql(f'PRAGMA user_version={version}')
        before = schema.objects(s.db.connection())
        with pytest.raises(SchemaError):
            s.initialize()
        assert schema.objects(s.db.connection()) == before
        assert s.db.execute_sql('SELECT * FROM foreign_data').fetchall() == [('keep',)]
        assert s.db.execute_sql('PRAGMA user_version').fetchone() == (version,)


def test_drift(tmp_path):
    with Store(tmp_path / 'db') as s:
        s.initialize()
        s.db.execute_sql('DROP INDEX notes_notebook_id_id')
        with pytest.raises(SchemaError):
            s.initialize()
        assert s.db.execute_sql('PRAGMA user_version').fetchone() == (1,)


def test_failed_initialization_rollback(tmp_path, monkeypatch):
    with Store(tmp_path / 'db') as s:
        original = s.db.execute_sql
        def fail(sql, *args, **kwargs):
            if sql == 'PRAGMA user_version=1':
                raise RuntimeError('injected')
            return original(sql, *args, **kwargs)
        monkeypatch.setattr(s.db, 'execute_sql', fail)
        with pytest.raises(RuntimeError):
            s.initialize()
        assert schema.objects(s.db.connection()) == []
        assert original('PRAGMA user_version').fetchone() == (0,)


@pytest.mark.parametrize('old,new', [
    ('name TEXT NOT NULL UNIQUE', 'name TEXT UNIQUE'),
    ('ON DELETE CASCADE', 'ON DELETE RESTRICT'),
    ("DEFAULT ''", "DEFAULT ' '"),
    ('CHECK(length(trim(title)) > 0)', 'CHECK(length(title) > 0)'),
    ('notes(notebook_id,id)', 'notes(id,notebook_id)'),
])
def test_structural_drift_refused_without_mutation(tmp_path, old, new):
    with Store(tmp_path / 'db') as s:
        for sql in schema.DDL:
            s.db.execute_sql(sql.replace(old, new))
        s.db.execute_sql('PRAGMA user_version=1')
        before = schema.objects(s.db.connection())
        with pytest.raises(SchemaError):
            s.initialize()
        assert schema.objects(s.db.connection()) == before
        assert s.db.execute_sql('PRAGMA user_version').fetchone() == (1,)
