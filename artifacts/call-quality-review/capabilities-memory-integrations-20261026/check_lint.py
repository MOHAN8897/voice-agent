"""Compare touched-file lint with HEAD; preserve existing unrelated debt."""
import collections
import json
from pathlib import Path
import subprocess
import tempfile

root = Path(__file__).resolve().parents[3]
changed = subprocess.check_output(['git', 'diff', '--name-only', '--', '*.py'], cwd=root, text=True).splitlines()
new = subprocess.check_output(['git', 'ls-files', '--others', '--exclude-standard', 'server/*.py', 'server/**/*.py'], cwd=root, text=True).splitlines()
paths = changed + [p for p in new if p not in changed]


def findings(base, names):
    result = subprocess.run(['python', '-m', 'ruff', 'check', '--output-format=json', *[str(base / p) for p in names]], capture_output=True, text=True, encoding='utf-8')
    rows = json.loads(result.stdout)
    out = []
    for row in rows:
        file = Path(row['filename'])
        source = file.read_text(encoding='utf-8').splitlines()
        out.append((file.relative_to(base).as_posix(), row['code'], row['message'], source[row['location']['row'] - 1].strip()))
    return out


with tempfile.TemporaryDirectory(prefix='voice-lint-') as directory:
    baseline = Path(directory)
    for name in changed:
        dest = baseline / name
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(subprocess.check_output(['git', 'show', 'HEAD:' + name], cwd=root))
    old = findings(baseline, changed)
    current = findings(root, paths)
    delta = list((collections.Counter(current) - collections.Counter(old)).elements())
    report = {'baseline_count': len(old), 'current_count': len(current), 'introduced': delta}
    Path(__file__).with_name('lint-results.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
    print(json.dumps(report, indent=2))
