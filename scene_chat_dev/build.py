from pathlib import Path
import zipfile,json
p=Path('scene_chat_dev/local.story.operit_bridge');a=Path('scene_chat_dev/artifacts');a.mkdir(exist_ok=True);target=a/'故事桥接-continuous-1.9.0.toolpkg'
with zipfile.ZipFile(target,'w',zipfile.ZIP_DEFLATED) as z:
 for f in p.rglob('*'):
  if f.is_file() and ".bak" not in f.name and ".into-backup-" not in f.name and not f.name.startswith("."):z.write(f,f.relative_to(p))
with zipfile.ZipFile(target) as z:
 assert json.loads(z.read('manifest.json'))['version']=='1.9.0'
 assert z.testzip() is None
print('ARCHIVE_OK',target.resolve())
