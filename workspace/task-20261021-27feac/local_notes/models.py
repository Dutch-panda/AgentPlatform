"""Models are constructed per Store, never globally bound."""
from dataclasses import dataclass
from peewee import Model, AutoField, TextField, ForeignKeyField


@dataclass(frozen=True)
class Notebook:
    id: int
    name: str
    created_at: str


@dataclass(frozen=True)
class Note:
    id: int
    notebook_id: int
    title: str
    body: str
    created_at: str
    updated_at: str


def bind_models(db):
    class Base(Model):
        class Meta:
            database = db
    class NotebookModel(Base):
        id = AutoField()
        name = TextField()
        created_at = TextField()
        class Meta:
            table_name = 'notebooks'
    class NoteModel(Base):
        id = AutoField()
        notebook = ForeignKeyField(NotebookModel, column_name='notebook_id',
                                   on_delete='CASCADE', index=False)
        title = TextField()
        body = TextField()
        created_at = TextField()
        updated_at = TextField()
        class Meta:
            table_name = 'notes'
    return NotebookModel, NoteModel
