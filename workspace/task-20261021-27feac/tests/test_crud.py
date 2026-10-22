import pytest
from peewee import IntegrityError
from local_notes import Store, NotFoundError


def test_complete_crud(store, tmp_path):
    s = store
    a = s.create_notebook("中文'; DROP TABLE notes;--")
    b = s.create_notebook('b')
    assert s.list_notebooks() == [a,b]
    assert s.rename_notebook(a.id, 'renamed').name == 'renamed'
    n = s.create_note(a.id, '标题', '')
    m = s.create_note(a.id, '标题', 'literal SELECT *')
    assert s.list_notes(a.id) == [n,m]
    changed = s.update_note(n.id, notebook_id=b.id, title='new', body='')
    assert changed.notebook_id == b.id and changed.body == ''
    assert changed.updated_at.endswith('Z')
    assert s.list_notes(a.id) == [m]
    s.delete_note(m.id)
    s.delete_notebook(a.id)
    with Store(tmp_path / 'notes.db') as reopened:
        reopened.require_schema()
        assert reopened.get_note(n.id) == changed
    s.delete_notebook(b.id)
    assert s.list_notes(b.id) == []
    assert n.title == '标题'  # detached immutable value


@pytest.mark.parametrize('method,args', [('get_note',(999,)),('delete_note',(999,)),
 ('get_notebook',(-1,)),('rename_notebook',(0,'x')),('delete_notebook',(999,))])
def test_missing(store, method, args):
    with pytest.raises(NotFoundError):
        getattr(store,method)(*args)


def test_integrity_and_move(store):
    a = store.create_notebook('A')
    with pytest.raises(IntegrityError): store.create_notebook('A')
    with pytest.raises(IntegrityError): store.create_note(999,'title')
    n = store.create_note(a.id, 'x')
    with pytest.raises(IntegrityError): store.update_note(n.id, notebook_id=999)
    with pytest.raises(NotFoundError): store.update_note(999, notebook_id=999)
    with pytest.raises(ValueError): store.update_note(n.id)
    assert store.get_note(n.id) == n
