from pathlib import Path
import json
import re
import zipfile

base = Path(__file__).resolve().parent
p = base / 'local.story.operit_bridge'
manifest = json.loads((p / 'manifest.json').read_text(encoding='utf-8'))
version = manifest['version']
main_js = (p / 'main.js').read_text(encoding='utf-8')
m_ver = re.search(r"const\s+PLUGIN_VERSION\s*=\s*['\"]([^'\"]+)['\"]", main_js)
assert m_ver and m_ver.group(1) == version, f"PLUGIN_VERSION mismatch: {m_ver and m_ver.group(1)} != {version}"
a = base / 'artifacts'
a.mkdir(exist_ok=True)
target = a / f'故事桥接-continuous-{version}.toolpkg'
with zipfile.ZipFile(target, 'w', zipfile.ZIP_DEFLATED) as z:
    for f in sorted(p.rglob('*')):
        rel = f.relative_to(p)
        if (
            f.is_file()
            and '.bak' not in f.name
            and '.into-backup-' not in f.name
            and not any(part.startswith('.') for part in rel.parts)
        ):
            z.write(f, rel.as_posix())
with zipfile.ZipFile(target) as z:
    assert json.loads(z.read('manifest.json'))['version'] == version
    assert z.testzip() is None
removed = []
for old in sorted(a.glob('故事桥接-continuous-*.toolpkg')):
    if old.resolve() != target.resolve():
        old.unlink()
        removed.append(old.name)
if removed:
    print('CLEANED_OLD', ', '.join(removed))
print('ARCHIVE_OK', target.resolve())
