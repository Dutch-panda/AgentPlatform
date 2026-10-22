import pytest
from local_notes import Store


@pytest.fixture
def store(tmp_path):
    with Store(tmp_path / 'notes.db') as s:
        s.initialize()
        yield s
