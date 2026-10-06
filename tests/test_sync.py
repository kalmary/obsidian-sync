import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
import sys
import fcntl

BINARY = Path(os.environ.get("UNISON_BINARY", str(Path.home() / ".local/share/obsidian-sync/unison-2.54.0")))


class SyncTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='obsidian-sync-test-')
        self.addCleanup(self.temp.cleanup)
        self.home = Path(self.temp.name)
        self.left = self.home / 'Documents/OBSIDIAN_VAULTS'
        self.right = self.home / 'Library/Mobile Documents/iCloud~md~obsidian/Documents'
        for root in (self.left, self.right):
            root.mkdir(parents=True)
            (root / 'keep.md').write_text('keep')

    def run_sync(self, expected=0):
        result = subprocess.run([sys.executable, "-m", "obsidian_sync.cli", "--unison", str(BINARY)], env={**os.environ, 'HOME': str(self.home)},
                                capture_output=True, text=True)
        log = self.home / 'Library/Logs/obsidian-sync.log'
        output = result.stdout + result.stderr + (log.read_text() if log.exists() else '')
        self.assertEqual(result.returncode, expected, output)
        return output

    def baseline(self):
        (self.left / 'note.md').write_text('original')
        (self.right / 'note.md').write_text('original')
        self.run_sync()

    def test_deletions_from_either_side(self):
        self.baseline()
        (self.left / 'note.md').unlink()
        self.run_sync()
        self.assertFalse((self.right / 'note.md').exists())
        (self.right / 'other.md').write_text('new')
        self.run_sync()
        (self.right / 'other.md').unlink()
        self.run_sync()
        self.assertFalse((self.left / 'other.md').exists())

    def test_conflicting_edits_preserved(self):
        self.baseline()
        (self.left / 'note.md').write_text('left edit')
        (self.right / 'note.md').write_text('right edit')
        self.run_sync(expected=1)
        self.assertEqual((self.left / 'note.md').read_text(), 'left edit')
        self.assertEqual((self.right / 'note.md').read_text(), 'right edit')

    def test_additions_and_edits_both_sides(self):
        (self.left / 'local.md').write_text('local')
        (self.right / 'cloud.md').write_text('cloud')
        self.run_sync()
        self.assertEqual((self.right / 'local.md').read_text(), 'local')
        self.assertEqual((self.left / 'cloud.md').read_text(), 'cloud')
        original = (self.left / 'local.md').stat()
        (self.left / 'local.md').write_text('LOCAL')
        os.utime(self.left / 'local.md', ns=(original.st_atime_ns, original.st_mtime_ns))
        (self.right / 'cloud.md').write_text('cloud edit')
        self.run_sync()
        self.assertEqual((self.right / 'local.md').read_text(), 'LOCAL')
        self.assertEqual((self.left / 'cloud.md').read_text(), 'cloud edit')

    def test_delete_edit_conflict(self):
        self.baseline()
        (self.left / 'note.md').unlink()
        (self.right / 'note.md').write_text('cloud edit')
        self.run_sync(expected=1)
        self.assertFalse((self.left / 'note.md').exists())
        self.assertEqual((self.right / 'note.md').read_text(), 'cloud edit')

    def test_placeholders_abort_before_copy(self):
        (self.right / '.note.md.icloud').touch()
        (self.left / 'new.md').write_text('new')
        self.run_sync(expected=2)
        self.assertFalse((self.right / 'new.md').exists())

    def test_missing_root_is_not_recreated(self):
        shutil.rmtree(self.right)
        self.run_sync(expected=2)
        self.assertFalse(self.right.exists())

    def test_exclusions(self):
        for name in ('.git', '.debris'):
            (self.left / name).mkdir()
            (self.left / name / 'data').write_text('private')
        self.run_sync()
        self.assertFalse((self.right / '.git').exists())
        self.assertFalse((self.right / '.debris').exists())

    def test_backup_on_overwrite_and_delete(self):
        self.baseline()
        (self.left / 'note.md').write_text('updated')
        self.run_sync()
        (self.left / 'note.md').unlink()
        self.run_sync()
        backups = self.home / '.local/state/obsidian-sync/backups'
        contents = [p.read_text() for p in backups.rglob('*') if p.is_file()]
        self.assertIn('original', contents)
        self.assertIn('updated', contents)

    def test_directory_rename(self):
        folder = self.left / 'Zażółć gęślą'
        folder.mkdir()
        (folder / 'note.md').write_text('note')
        self.run_sync()
        folder.rename(self.left / 'renamed')
        self.run_sync()
        self.assertFalse((self.right / 'Zażółć gęślą').exists())
        self.assertEqual((self.right / 'renamed/note.md').read_text(), 'note')

    def test_empty_replica_aborts(self):
        self.baseline()
        for path in self.left.iterdir():
            path.unlink()
        self.run_sync(expected=2)
        self.assertTrue((self.right / 'note.md').exists())

    def test_overlapping_run_is_skipped(self):
        state = self.home / '.local/state/obsidian-sync'
        state.mkdir(parents=True)
        with (state / 'lock').open('a') as lock:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            (self.left / 'new.md').write_text('new')
            output = self.run_sync()
            self.assertIn('Another sync is running', output)
            self.assertFalse((self.right / 'new.md').exists())

    def test_leftover_lock_file_does_not_block(self):
        state = self.home / '.local/state/obsidian-sync'
        state.mkdir(parents=True)
        (state / 'lock').touch()
        (self.left / 'new.md').write_text('new')
        self.run_sync()
        self.assertEqual((self.right / 'new.md').read_text(), 'new')

    def test_missing_sync_history_aborts(self):
        self.baseline()
        state = self.home / '.local/state/obsidian-sync'
        shutil.rmtree(state / 'archives')
        (self.left / 'note.md').unlink()
        self.run_sync(expected=2)
        self.assertTrue((self.right / 'note.md').exists())

    def test_unrelated_archives_do_not_replace_sync_history(self):
        self.baseline()
        archives = self.home / '.local/state/obsidian-sync/archives'
        for path in archives.glob('ar*'):
            path.unlink()
        (archives / 'ar-unrelated-one').touch()
        (archives / 'ar-unrelated-two').touch()
        (self.left / 'note.md').unlink()
        self.run_sync(expected=2)
        self.assertTrue((self.right / 'note.md').exists())

    def test_initial_conflict_preserves_both_versions(self):
        (self.left / 'note.md').write_text('left')
        (self.right / 'note.md').write_text('right')
        self.run_sync(expected=1)
        self.assertEqual((self.left / 'note.md').read_text(), 'left')
        self.assertEqual((self.right / 'note.md').read_text(), 'right')

    def test_lock_is_retained_by_running_engine(self):
        engine = self.home / 'engine.py'
        engine.write_text(
            '#!/opt/homebrew/bin/python3\n'
            'import os, time\n'
            'from pathlib import Path\n'
            'Path(os.environ["HOME"], "started").touch()\n'
            'while not Path(os.environ["HOME"], "finished").exists():\n'
            '    time.sleep(0.02)\n'
        )
        engine.chmod(0o755)
        parent = subprocess.Popen(
            [sys.executable, '-m', 'obsidian_sync.cli', '--unison', str(engine)],
            env={**os.environ, 'HOME': str(self.home)},
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )
        import time
        try:
            deadline = time.monotonic() + 5
            while not (self.home / 'started').exists():
                self.assertLess(time.monotonic(), deadline, 'Engine did not start')
                time.sleep(0.02)
            parent.terminate()
            parent.wait(timeout=5)
            output = self.run_sync()
            self.assertIn('Another sync is running', output)
        finally:
            (self.home / 'finished').touch()
            if parent.poll() is None:
                parent.terminate()
                parent.wait(timeout=5)


if __name__ == '__main__':
    unittest.main()
