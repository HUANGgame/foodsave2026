"""Exercise the delivered ZIP's fallback behavior, entirely in temporary storage."""
import importlib.util
import json
from pathlib import Path
import subprocess
import types
import zipfile


def test_candidate_preserves_verified_fallback_and_persistent_precedence(tmp_path, monkeypatch):
    root = Path(__file__).resolve().parents[2]
    spec = importlib.util.spec_from_file_location('candidate_builder', root/'release/20261006/build_backend_candidate.py')
    builder = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(builder)
    source = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=root, text=True).strip()
    output = tmp_path/'candidate'
    manifest = builder.build(source, output)
    with zipfile.ZipFile(output/manifest['file']) as archive:
        assert builder.FALLBACK in archive.namelist()
        assert not any(n.startswith(('home/', 'tests/', 'migrations/')) for n in archive.namelist())
        for excluded in builder.EXCLUDED:
            assert f'foodsave/{excluded}' not in archive.namelist()
        archive.extractall(tmp_path/'runtime')
    runtime = tmp_path/'runtime/foodsave'
    module = types.ModuleType('candidate_demo_prizes')
    module.__file__ = str(runtime/'demo_prizes.py')
    exec(compile((runtime/'demo_prizes.py').read_bytes(), module.__file__, 'exec'), module.__dict__)
    store = tmp_path/'data';store.mkdir()
    path = store/'demo-prizes.json'
    monkeypatch.setenv('FOODSAVE_DEMO_PRIZES_ENABLED', 'true')
    monkeypatch.setenv('FOODSAVE_DEMO_PRIZE_STORE', str(path))
    fallback_bytes = (runtime/'static/demo-prizes.json').read_bytes()
    expected = json.loads(fallback_bytes)
    assert module.read() == expected
    assert not path.exists()
    monkeypatch.setattr(module.secrets, 'randbelow', lambda n: 0)
    draw = module.draw(expected['revision'])
    assert draw['redeemable'] is False and draw['consumes_real_spin'] is False
    assert not path.exists()
    persisted = {**expected, 'revision': expected['revision'] + 10}
    path.write_text(json.dumps(persisted))
    before = path.read_bytes()
    assert module.read() == persisted
    assert path.read_bytes() == before
    assert (runtime/'static/demo-prizes.json').read_bytes() == fallback_bytes
