import json
import subprocess
import sys
from local_notes.__main__ import main
import pytest


def call(path, *args):
    return subprocess.run([sys.executable,'-m','local_notes','--db',str(path),*args],
                          capture_output=True,text=True)


def test_cli(tmp_path):
    path = tmp_path / 'space dir' / 'notes.db'
    assert call(path,'notebook','list').returncode == 1
    assert not path.exists()
    assert call(path,'init').returncode == 0
    assert json.loads(call(path,'notebook','add','中文').stdout)['id'] == 1
    assert call(path,'notebook','add','中文').returncode == 3
    assert call(path,'notebook','get','1').returncode == 0
    assert call(path,'notebook','rename','1','renamed').returncode == 0
    assert len(json.loads(call(path,'notebook','list').stdout)) == 1
    assert call(path,'note','add','--notebook-id','1','--title','x').returncode == 0
    assert call(path,'note','get','1').returncode == 0
    assert len(json.loads(call(path,'note','list','--notebook-id','1').stdout)) == 1
    assert call(path,'note','update','1').returncode == 2
    assert call(path,'note','update','1','--body','').returncode == 0
    assert call(path,'note','delete','1').returncode == 0
    assert call(path,'notebook','delete','1').returncode == 0
    missing = call(path,'note','get','1')
    assert missing.returncode == 1 and 'not found' in missing.stderr
    assert 'Traceback' not in missing.stderr
    assert call(path,'note','get','bad').returncode == 2
    assert call(path,'note','add','--notebook-id','999','--title','x').returncode == 3


def test_unexpected_errors_not_hidden(tmp_path, monkeypatch):
    def bug(*a): raise RuntimeError('bug')
    monkeypatch.setattr('local_notes.__main__.Store', bug)
    with pytest.raises(RuntimeError):
        main(['--db', str(tmp_path/'db'), 'init'])
