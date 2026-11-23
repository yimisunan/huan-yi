"""Unit tests for 一键同步GitHub.py covering add/update/delete, save protection, prune, rollback, and safety guards."""
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
import zipfile

ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location('github_sync', ROOT / '一键同步GitHub.py')
MOD = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MOD)


def _make_github_zip(dest_zip: Path, files: dict[str, bytes | str], top_dir: str = 'huan-yi-main') -> None:
    with zipfile.ZipFile(dest_zip, 'w', zipfile.ZIP_DEFLATED) as zf:
        for rel, content in files.items():
            data = content.encode('utf-8') if isinstance(content, str) else content
            zf.writestr(f'{top_dir}/{rel}', data)


class GitHubSyncTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.base = Path(self.tmp.name)
        self.work = self.base / 'project'
        self.work.mkdir()
        # Seed minimal local project with player saves + runtime state + obsolete files.
        (self.work / '语音运行.py').write_text('print("old server")\n', encoding='utf-8')
        (self.work / 'story_service.py').write_text('# old service v1\n', encoding='utf-8')
        (self.work / 'data.json').write_text('{"round": 12, "player": "REAL_SAVE"}\n', encoding='utf-8')
        (self.work / 'voice_config.json').write_text('{"沈知韫": {"voice": "custom"}}\n', encoding='utf-8')
        (self.work / '存档').mkdir()
        (self.work / '存档/全局记忆库.txt').write_text('玩家真实进度L1记忆\n', encoding='utf-8')
        (self.work / '.round-runtime/interaction').mkdir(parents=True)
        (self.work / '.round-runtime/interaction/000001.json').write_text('{"seq":1}\n', encoding='utf-8')
        (self.work / '语音仓库').mkdir()
        (self.work / '语音仓库/voice_repo.json').write_text('{"fav": true}\n', encoding='utf-8')
        (self.work / '.env').write_text('FISH_API_KEY=secret\n', encoding='utf-8')
        # Seed realistic root .git/ repository metadata that must NEVER be touched.
        (self.work / '.git/refs/heads').mkdir(parents=True)
        (self.work / '.git/objects/pack').mkdir(parents=True)
        (self.work / '.git/HEAD').write_text('ref: refs/heads/main\n', encoding='utf-8')
        (self.work / '.git/config').write_text('[core]\n\trepositoryformatversion = 0\n', encoding='utf-8')
        (self.work / '.git/index').write_bytes(b'DIRC\x00\x00\x00\x02mock-index')
        (self.work / '.git/refs/heads/main').write_text('0123456789abcdef0123456789abcdef01234567\n', encoding='utf-8')
        (self.work / '.git/objects/pack/mock.pack').write_bytes(b'PACK\x00\x00\x00\x02')
        # Obsolete local files not on GitHub anymore.
        (self.work / '开发者功能/修订日志/2026.11/旧碎片.md').parent.mkdir(parents=True)
        (self.work / '开发者功能/修订日志/2026.11/旧碎片.md').write_text('old fragment\n', encoding='utf-8')
        (self.work / 'scene_chat_dev/artifacts').mkdir(parents=True)
        (self.work / 'scene_chat_dev/artifacts/故事桥接-continuous-1.9.5.toolpkg').write_bytes(b'oldpkg')
        # User custom .nomedia should never be pruned.
        (self.work / 'custom_dir').mkdir()
        (self.work / 'custom_dir/.nomedia').write_bytes(b'')

    def tearDown(self):
        self.tmp.cleanup()

    def test_first_sync_prune_protects_all_saves_and_backs_up_changes(self):
        zip1 = self.base / 'v1.zip'
        _make_github_zip(zip1, {
            '语音运行.py': 'print("old server")\n',
            'story_service.py': '# new service v2\n',
            'story_compiler.py': '# brand new compiler\n',
            'data.json': '{"round": 0, "blank": true}\n',
            'voice_config.json': '{"default": true}\n',
            '存档/全局记忆库.txt': '空档初始模板\n',
            '存档/save_state.json': '{"version": 2, "blank": true}\n',
            '存档/四层记忆.json': '{"version": 1, "layers": {}}\n',
            '存档/近期演播.json': '{"version": 1, "segments": []}\n',
            '存档/徐志北道具图鉴.txt': '空档道具模板\n',
            'scene_chat_dev/.nomedia': b'',
            'scene_chat_dev/artifacts/故事桥接-continuous-2.1.2.toolpkg': b'newpkg',
            '开发者功能/修订日志/README.md': '# 索引\n',
        })
        extract_dir = self.base / 'ext1'
        remote_root, ref = MOD.extract_github_zip(zip1, extract_dir)
        plan = MOD.compute_sync_plan(self.work, remote_root)

        self.assertIn('story_compiler.py', plan['to_add'])
        self.assertIn('scene_chat_dev/.nomedia', plan['to_add'])
        self.assertIn('story_service.py', plan['to_update'])
        # Because 存档/ already holds a real legacy save, NO remote 存档/* seed templates may be injected!
        for rel in (
            'data.json',
            'voice_config.json',
            '存档/全局记忆库.txt',
            '存档/save_state.json',
            '存档/四层记忆.json',
            '存档/近期演播.json',
            '存档/徐志北道具图鉴.txt',
        ):
            self.assertIn(rel, plan['protected_skipped'])
            self.assertNotIn(rel, plan['to_add'])
            self.assertNotIn(rel, plan['to_update'])
        self.assertIn('开发者功能/修订日志/2026.11/旧碎片.md', plan['extra_untracked'])
        self.assertIn('scene_chat_dev/artifacts/故事桥接-continuous-1.9.5.toolpkg', plan['extra_untracked'])
        # Local-only, .git/, and user .nomedia must never appear in extra_untracked.
        self.assertNotIn('.env', plan['extra_untracked'])
        self.assertNotIn('.git/HEAD', plan['extra_untracked'])
        self.assertNotIn('.git/config', plan['extra_untracked'])
        self.assertNotIn('custom_dir/.nomedia', plan['extra_untracked'])

        summary = MOD.apply_sync_plan(self.work, plan, prune_extra=True, source_ref=ref)
        self.assertEqual(summary['updated'], 1)
        self.assertEqual(summary['deleted'], 2)
        self.assertEqual(summary['protected'], 7)
        self.assertEqual(summary['changed_toolpkgs'], ['scene_chat_dev/artifacts/故事桥接-continuous-2.1.2.toolpkg'])
        self.assertEqual(summary['added_nomedia'], ['scene_chat_dev/.nomedia'])
        self.assertTrue(summary['legacy_save_pending_migration'])
        self.assertFalse(summary['self_updated'])

        # Verify updated & added files, and confirm empty P2 templates were NOT injected into legacy 存档/.
        self.assertEqual((self.work / 'story_service.py').read_text(encoding='utf-8'), '# new service v2\n')
        self.assertEqual((self.work / 'story_compiler.py').read_text(encoding='utf-8'), '# brand new compiler\n')
        self.assertFalse((self.work / '存档/save_state.json').exists())
        self.assertFalse((self.work / '存档/四层记忆.json').exists())
        self.assertFalse((self.work / '存档/近期演播.json').exists())
        self.assertFalse((self.work / '存档/徐志北道具图鉴.txt').exists())
        self.assertTrue((self.work / 'scene_chat_dev/.nomedia').is_file())

        # Verify obsolete files were removed and empty directory cleaned up.
        self.assertFalse((self.work / '开发者功能/修订日志/2026.11/旧碎片.md').exists())
        self.assertFalse((self.work / '开发者功能/修订日志/2026.11').exists())
        self.assertFalse((self.work / 'scene_chat_dev/artifacts/故事桥接-continuous-1.9.5.toolpkg').exists())

        # Verify ALL player saves, runtime files, secrets, and .git/ are 100% untouched!
        self.assertEqual((self.work / 'data.json').read_text(encoding='utf-8'), '{"round": 12, "player": "REAL_SAVE"}\n')
        self.assertEqual((self.work / 'voice_config.json').read_text(encoding='utf-8'), '{"沈知韫": {"voice": "custom"}}\n')
        self.assertEqual((self.work / '存档/全局记忆库.txt').read_text(encoding='utf-8'), '玩家真实进度L1记忆\n')
        self.assertEqual((self.work / '.round-runtime/interaction/000001.json').read_text(encoding='utf-8'), '{"seq":1}\n')
        self.assertEqual((self.work / '语音仓库/voice_repo.json').read_text(encoding='utf-8'), '{"fav": true}\n')
        self.assertEqual((self.work / '.env').read_text(encoding='utf-8'), 'FISH_API_KEY=secret\n')
        self.assertEqual((self.work / '.git/HEAD').read_text(encoding='utf-8'), 'ref: refs/heads/main\n')
        self.assertEqual((self.work / '.git/config').read_text(encoding='utf-8'), '[core]\n\trepositoryformatversion = 0\n')
        self.assertEqual((self.work / '.git/index').read_bytes(), b'DIRC\x00\x00\x00\x02mock-index')
        self.assertTrue((self.work / 'custom_dir/.nomedia').is_file())

        # Verify rollback restores previous files and removes newly added managed files (but keeps saves & .git untouched!).
        rb = MOD.rollback_latest(self.work)
        self.assertGreaterEqual(rb['restored'], 3)
        self.assertEqual((self.work / 'story_service.py').read_text(encoding='utf-8'), '# old service v1\n')
        self.assertTrue((self.work / '开发者功能/修订日志/2026.11/旧碎片.md').is_file())
        self.assertFalse((self.work / 'story_compiler.py').exists())
        self.assertEqual((self.work / '存档/全局记忆库.txt').read_text(encoding='utf-8'), '玩家真实进度L1记忆\n')
        self.assertEqual((self.work / 'data.json').read_text(encoding='utf-8'), '{"round": 12, "player": "REAL_SAVE"}\n')
        self.assertEqual((self.work / '.git/config').read_text(encoding='utf-8'), '[core]\n\trepositoryformatversion = 0\n')

    def test_subsequent_sync_auto_deletes_github_removed_tracked_files(self):
        # First sync establishes .sync-state.json tracking.
        zip1 = self.base / 's1.zip'
        _make_github_zip(zip1, {
            '语音运行.py': 'v1',
            'story_service.py': 'v1',
            'temp_module.py': 'will be deleted later',
        })
        r1, ref1 = MOD.extract_github_zip(zip1, self.base / 'e1')
        p1 = MOD.compute_sync_plan(self.work, r1)
        MOD.apply_sync_plan(self.work, p1, prune_extra=False, source_ref=ref1)
        self.assertTrue((self.work / 'temp_module.py').is_file())

        # Second sync deletes temp_module.py on GitHub -> automatically detected in to_delete_tracked!
        zip2 = self.base / 's2.zip'
        _make_github_zip(zip2, {
            '语音运行.py': 'v1',
            'story_service.py': 'v2',
        })
        r2, ref2 = MOD.extract_github_zip(zip2, self.base / 'e2')
        p2 = MOD.compute_sync_plan(self.work, r2)
        self.assertEqual(p2['to_delete_tracked'], ['temp_module.py'])
        MOD.apply_sync_plan(self.work, p2, prune_extra=False, source_ref=ref2)
        self.assertFalse((self.work / 'temp_module.py').exists())
        self.assertEqual((self.work / 'story_service.py').read_text(encoding='utf-8'), 'v2')

    def test_incremental_manifest_only_stages_changed_files(self):
        old_server = (self.work / '语音运行.py').read_bytes()
        new_service = b'# incremental v3\n'
        remote_entries = {
            '语音运行.py': {'sha': MOD.git_blob_sha1_bytes(old_server), 'size': len(old_server)},
            'story_service.py': {'sha': MOD.git_blob_sha1_bytes(new_service), 'size': len(new_service)},
            'data.json': {'sha': MOD.git_blob_sha1_bytes(b'{"blank":true}'), 'size': 14},
            '.git/config': {'sha': MOD.git_blob_sha1_bytes(b'evil'), 'size': 4},
        }
        plan = MOD.compute_sync_plan_from_manifest(self.work, remote_entries)
        self.assertEqual(plan['to_update'], ['story_service.py'])
        self.assertEqual(plan['to_add'], [])
        self.assertEqual(plan['download_bytes'], len(new_service))
        self.assertIn('data.json', plan['protected_skipped'])
        staged_path = self.base / 'staged_service.py'
        staged_path.write_bytes(new_service)
        res = MOD.apply_sync_plan(self.work, plan, staged_files={'story_service.py': staged_path})
        self.assertEqual(res['updated'], 1)
        self.assertEqual((self.work / 'story_service.py').read_bytes(), new_service)
        self.assertEqual((self.work / 'data.json').read_text(encoding='utf-8'), '{"round": 12, "player": "REAL_SAVE"}\n')
        self.assertEqual((self.work / '.git/config').read_text(encoding='utf-8'), '[core]\n\trepositoryformatversion = 0\n')

    def test_root_git_dir_is_hard_protected_across_sync_prune_and_rollback(self):
        # 1. Path classification: block any .git (any case/depth), allow .gitignore and .github/.
        for blocked in ('.git', '.git/config', '.GIT/HEAD', 'nested/.git/index', '.git\\config'):
            self.assertTrue(MOD.is_git_metadata_path(blocked), blocked)
            self.assertTrue(MOD.is_local_only(blocked), blocked)
        for allowed in ('.gitignore', '.github/workflows/ci.yml', '一键同步GitHub.py'):
            self.assertFalse(MOD.is_git_metadata_path(allowed), allowed)
            self.assertFalse(MOD.is_local_only(allowed), allowed)

        # 2. ZIP containing .git/* entries must ignore them during extraction and sync + prune.
        dirty_zip = self.base / 'dirty_with_git.zip'
        _make_github_zip(dirty_zip, {
            '语音运行.py': 'print("old server")\n',
            'story_service.py': '# clean update\n',
            '.gitignore': '.git/\n',
            '.git/config': '[core]\n\tcorrupted = true\n',
            '.git/HEAD': 'corrupted-head\n',
            '.GIT/hooks/pre-commit': '#!/bin/sh\necho evil\n',
        })
        remote_root, ref = MOD.extract_github_zip(dirty_zip, self.base / 'dirty_ext')
        self.assertFalse((remote_root / '.git').exists())
        self.assertFalse((remote_root / '.GIT').exists())
        plan = MOD.compute_sync_plan(self.work, remote_root)
        self.assertIn('.gitignore', plan['to_add'])
        for bucket in ('to_add', 'to_update', 'to_delete_tracked', 'extra_untracked'):
            for rel in plan[bucket]:
                self.assertFalse(MOD.is_git_metadata_path(rel), f'{rel} leaked into {bucket}')
        MOD.apply_sync_plan(self.work, plan, prune_extra=True, source_ref=ref)
        self.assertEqual((self.work / '.git/HEAD').read_text(encoding='utf-8'), 'ref: refs/heads/main\n')
        self.assertEqual((self.work / '.git/config').read_text(encoding='utf-8'), '[core]\n\trepositoryformatversion = 0\n')
        self.assertEqual((self.work / '.git/refs/heads/main').read_text(encoding='utf-8'), '0123456789abcdef0123456789abcdef01234567\n')

        # 3. Direct firewall in apply_sync_plan rejects tampered plans targeting .git/.
        fake_src = self.base / 'tamper.txt'
        fake_src.write_text('tampered', encoding='utf-8')
        base_plan = {
            'remote_files': {},
            'remote_hashes': {},
            'to_add': [],
            'to_update': [],
            'to_delete_tracked': [],
            'extra_untracked': [],
            'protected_skipped': [],
            'unchanged': [],
        }
        for key in ('to_add', 'to_update', 'to_delete_tracked'):
            bad_plan = {**base_plan, key: ['.git/config']}
            with self.assertRaises(RuntimeError):
                MOD.apply_sync_plan(self.work, bad_plan, staged_files={'.git/config': fake_src})
        bad_case_plan = {**base_plan, 'to_update': ['.GIT/HEAD']}
        with self.assertRaises(RuntimeError):
            MOD.apply_sync_plan(self.work, bad_case_plan, staged_files={'.GIT/HEAD': fake_src})

        # 4. Incremental downloader also rejects protected .git targets.
        with self.assertRaises(RuntimeError):
            MOD.download_incremental_files('o/r', 'deadbeef', ['.git/config'], {}, self.base / 'dl')

        # 5. Tampered backup manifest during rollback must NEVER overwrite or delete .git/ files.
        tampered_backup = self.work / '.sync-backup/99999999-999999'
        (tampered_backup / 'files/.git').mkdir(parents=True)
        (tampered_backup / 'files/.git/config').write_text('OVERWRITTEN_BY_ROLLBACK', encoding='utf-8')
        (tampered_backup / 'files/.git/HEAD').write_text('OVERWRITTEN_HEAD', encoding='utf-8')
        (tampered_backup / 'manifest.json').write_text(json.dumps({
            'created_at': '99999999-999999',
            'added': ['.git/index'],
            'updated': ['.git/config'],
            'deleted': ['.git/HEAD'],
        }), encoding='utf-8')
        rb = MOD.rollback_latest(self.work)
        self.assertEqual(rb['restored'], 0)
        self.assertEqual(rb['removed_added'], 0)
        self.assertEqual((self.work / '.git/config').read_text(encoding='utf-8'), '[core]\n\trepositoryformatversion = 0\n')
        self.assertEqual((self.work / '.git/HEAD').read_text(encoding='utf-8'), 'ref: refs/heads/main\n')
        self.assertEqual((self.work / '.git/index').read_bytes(), b'DIRC\x00\x00\x00\x02mock-index')

        # 6. Summary helper explicitly reports root .git/ protection.
        detected = MOD._detect_protected_local_items(self.work)
        self.assertTrue(any('.git/' in item for item in detected))

    def test_zip_slip_archive_rejected(self):
        bad_zip = self.base / 'bad.zip'
        with zipfile.ZipFile(bad_zip, 'w') as zf:
            zf.writestr('repo/../evil.txt', b'pwn')
        with self.assertRaises(ValueError):
            MOD.extract_github_zip(bad_zip, self.base / 'bad_ext')

    def test_fresh_install_empty_save_dir_seeds_entire_p2_bundle(self):
        # Simulate a fresh install where 存档/ has no real save files (only a hidden .nomedia marker).
        (self.work / '存档/全局记忆库.txt').unlink()
        (self.work / '存档/.nomedia').write_bytes(b'')
        zip_fresh = self.base / 'fresh.zip'
        p2_seed_files = {
            '存档/save_state.json': '{"version": 2}\n',
            '存档/四层记忆.json': '{"version": 1, "layers": {"L1": []}}\n',
            '存档/近期演播.json': '{"version": 1, "segments": []}\n',
            '存档/全局记忆库.txt': '初始只读视图\n',
            '存档/徐志北道具图鉴.txt': '初始道具图鉴\n',
        }
        _make_github_zip(zip_fresh, {
            '语音运行.py': 'print("old server")\n',
            'story_service.py': '# old service v1\n',
            **p2_seed_files,
        })
        remote_root, ref = MOD.extract_github_zip(zip_fresh, self.base / 'fresh_ext')
        plan = MOD.compute_sync_plan(self.work, remote_root)
        for rel in p2_seed_files:
            self.assertIn(rel, plan['to_add'])
            self.assertNotIn(rel, plan['protected_skipped'])
        summary = MOD.apply_sync_plan(self.work, plan, prune_extra=False, source_ref=ref)
        self.assertEqual(summary['added'], len(p2_seed_files))
        self.assertFalse(summary['legacy_save_pending_migration'])
        for rel, expected in p2_seed_files.items():
            self.assertEqual((self.work / rel).read_text(encoding='utf-8'), expected)
        # Seeded 存档/ files remain protected on rollback as well.
        MOD.rollback_latest(self.work)
        for rel in p2_seed_files:
            self.assertTrue((self.work / rel).is_file())

    def test_existing_p2_save_skips_missing_rendered_view_and_guards_journals(self):
        # Existing P2 save with save_state.json present, but rendered 徐志北道具图鉴.txt absent:
        # sync must NOT drop an empty template that would drift against save_state.json.
        (self.work / '存档/save_state.json').write_text('{"version": 2, "real": true}\n', encoding='utf-8')
        (self.work / '一键同步GitHub.py').write_text('# old sync script\n', encoding='utf-8')
        zip_p2 = self.base / 'p2_update.zip'
        _make_github_zip(zip_p2, {
            '语音运行.py': 'print("old server")\n',
            'story_service.py': '# old service v1\n',
            '一键同步GitHub.py': '# new sync script v2\n',
            '存档/save_state.json': '{"version": 2, "blank": true}\n',
            '存档/徐志北道具图鉴.txt': '空档道具模板\n',
        })
        remote_root, ref = MOD.extract_github_zip(zip_p2, self.base / 'p2_ext')
        plan = MOD.compute_sync_plan(self.work, remote_root)
        self.assertIn('存档/save_state.json', plan['protected_skipped'])
        self.assertIn('存档/徐志北道具图鉴.txt', plan['protected_skipped'])
        self.assertNotIn('存档/徐志北道具图鉴.txt', plan['to_add'])
        summary = MOD.apply_sync_plan(self.work, plan, prune_extra=False, source_ref=ref)
        self.assertTrue(summary['self_updated'])
        self.assertFalse(summary['legacy_save_pending_migration'])
        self.assertFalse((self.work / '存档/徐志北道具图鉴.txt').exists())

        # Pending runtime/reset journal guard checks.
        self.assertIsNone(MOD.detect_pending_runtime_journal(self.work))
        journal = self.work / '.round-runtime/journal.json'
        journal.write_text('{"stage":"writing"}\n', encoding='utf-8')
        hit = MOD.detect_pending_runtime_journal(self.work)
        self.assertIsNotNone(hit)
        self.assertEqual(hit[0], '.round-runtime/journal.json')
        self.assertIn('round_runtime.py recover', hit[1])
        reset_journal = self.work / '.round-runtime/reset-journal.json'
        reset_journal.write_text('{"stage":"reset"}\n', encoding='utf-8')
        hit_reset = MOD.detect_pending_runtime_journal(self.work)
        self.assertIsNotNone(hit_reset)
        self.assertEqual(hit_reset[0], '.round-runtime/reset-journal.json')
        self.assertIn('存档清理器.py --recover', hit_reset[1])

    def test_toolpkg_mtime_refresh_metadata_and_stale_detection(self):
        import io
        import os
        import time

        def _make_toolpkg_bytes(ver: str) -> bytes:
            buf = io.BytesIO()
            with zipfile.ZipFile(buf, 'w', zipfile.ZIP_DEFLATED) as zf:
                zf.writestr('manifest.json', json.dumps({'version': ver, 'toolpkg_id': 'local.story.operit_bridge'}))
            return buf.getvalue()

        # 1. Pre-existing toolpkg with yesterday's mtime gets overwritten -> mtime must refresh to now.
        pkg_rel = 'scene_chat_dev/artifacts/故事桥接-continuous-2.1.2.toolpkg'
        old_pkg = self.work / pkg_rel
        old_pkg.write_bytes(_make_toolpkg_bytes('2.1.2'))
        yesterday = time.time() - 86400
        os.utime(old_pkg, (yesterday, yesterday))
        self.assertLess(old_pkg.stat().st_mtime, time.time() - 3600)

        zip_same_name = self.base / 'same_name.zip'
        _make_github_zip(zip_same_name, {
            '语音运行.py': 'print("old server")\n',
            'story_service.py': '# old service v1\n',
            pkg_rel: _make_toolpkg_bytes('2.1.2') + b'\x00',
        })
        r1, ref1 = MOD.extract_github_zip(zip_same_name, self.base / 'ext_same')
        p1 = MOD.compute_sync_plan(self.work, r1)
        s1 = MOD.apply_sync_plan(self.work, p1, prune_extra=False, source_ref=ref1)
        self.assertGreater(old_pkg.stat().st_mtime, time.time() - 30)
        self.assertEqual(len(s1['changed_toolpkg_details']), 1)
        self.assertEqual(s1['changed_toolpkg_details'][0]['version'], '2.1.2')
        # 1.9.5 from setUp wasn't pruned because prune_extra=False -> must be reported in stale_toolpkgs!
        self.assertIn('scene_chat_dev/artifacts/故事桥接-continuous-1.9.5.toolpkg', s1['stale_toolpkgs'])

        # 2. Version bump 2.1.2 -> 2.1.3 automatically removes tracked 2.1.2 and reports 2.1.3 metadata.
        pkg_213 = 'scene_chat_dev/artifacts/故事桥接-continuous-2.1.3.toolpkg'
        zip_bump = self.base / 'bump_213.zip'
        _make_github_zip(zip_bump, {
            '语音运行.py': 'print("old server")\n',
            'story_service.py': '# old service v1\n',
            pkg_213: _make_toolpkg_bytes('2.1.3'),
        })
        r2, ref2 = MOD.extract_github_zip(zip_bump, self.base / 'ext_213')
        p2 = MOD.compute_sync_plan(self.work, r2)
        self.assertIn(pkg_rel, p2['to_delete_tracked'])
        self.assertIn(pkg_213, p2['to_add'])
        s2 = MOD.apply_sync_plan(self.work, p2, prune_extra=True, source_ref=ref2)
        self.assertFalse(old_pkg.exists())
        self.assertTrue((self.work / pkg_213).is_file())
        self.assertEqual(s2['stale_toolpkgs'], [])
        self.assertEqual(s2['changed_toolpkg_details'][0]['version'], '2.1.3')
        self.assertEqual(s2['changed_toolpkg_details'][0]['size'], (self.work / pkg_213).stat().st_size)

    def test_nomedia_presence_only_android_mediaprovider_content(self):
        """Android 11+ MediaProvider writes path/dirty metadata inside .nomedia files;
        existing .nomedia must be treated as unchanged and newly created .nomedia must
        not fail strict post-write SHA-1 comparison."""
        existing_nomedia = self.work / 'scene_chat_dev/.nomedia'
        existing_nomedia.parent.mkdir(parents=True, exist_ok=True)
        oem_bytes = b'/storage/emulated/0/huan-yi/scene_chat_dev\n'
        existing_nomedia.write_bytes(oem_bytes)

        zip_path = self.base / 'nomedia_android.zip'
        _make_github_zip(zip_path, {
            '语音运行.py': 'print("new server")\n',
            'story_service.py': '# old service v1\n',
            'scene_chat_dev/.nomedia': b'',
            'txt文件/image/.nomedia': b'',
        })
        remote_root, ref = MOD.extract_github_zip(zip_path, self.base / 'ext_nomedia')
        plan = MOD.compute_sync_plan(self.work, remote_root)

        # Existing .nomedia with Android MediaProvider bytes is skipped (unchanged), NOT updated.
        self.assertNotIn('scene_chat_dev/.nomedia', plan['to_update'])
        self.assertIn('scene_chat_dev/.nomedia', plan['unchanged'])
        # Missing .nomedia is still added.
        self.assertIn('txt文件/image/.nomedia', plan['to_add'])

        # Simulate Android MediaProvider immediately writing metadata into newly created .nomedia.
        orig_copy = MOD.atomic_copy_file

        def _android_fuse_copy(src: Path, dest: Path) -> None:
            orig_copy(src, dest)
            if dest.name == '.nomedia':
                dest.write_bytes(b'/storage/emulated/0/huan-yi/txt/image\n')

        MOD.atomic_copy_file = _android_fuse_copy
        try:
            summary = MOD.apply_sync_plan(self.work, plan, prune_extra=False, source_ref=ref)
        finally:
            MOD.atomic_copy_file = orig_copy

        self.assertEqual(existing_nomedia.read_bytes(), oem_bytes)
        self.assertTrue((self.work / 'txt文件/image/.nomedia').is_file())
        self.assertEqual(summary['added_nomedia'], ['txt文件/image/.nomedia'])
        self.assertEqual((self.work / '语音运行.py').read_text(encoding='utf-8'), 'print("new server")\n')


if __name__ == '__main__':
    unittest.main()
