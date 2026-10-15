import shutil
import unittest
from pathlib import Path
from unittest.mock import patch
import backup_compose
import test_backup


class ComposeBackupTests(unittest.TestCase):
    # Use the same isolated source and backup fixture; run only these additional cases.
    def setUp(self):
        test_backup.BackupTests.setUp(self)
        self.calls = []
        self.patch = patch.object(backup_compose, 'BASE', self.base)
        self.patch.start()
        self.addCleanup(self.patch.stop)

    def run_fake(self, args):
        self.calls.append(args)
        if args[0] == 'ps':
            return 'isolated-container'
        if args[0] == 'run':
            return '/data/backups/' + self.backup.name
        if args[0] == 'cp':
            shutil.copytree(self.backup, args[2])
        return ''

    def test_compose_success_restarts_before_copy(self):
        target = backup_compose.backup_stack(self.base / 'host', self.run_fake)
        self.assertTrue((target / 'manifest.json').exists())
        operations = [call[0] for call in self.calls]
        self.assertLess(operations.index('start'), operations.index('cp'))
        self.assertFalse((self.base / '.compose-backup.lock').exists())

    def test_compose_failure_restarts_service(self):
        def failure(args):
            if args[0] == 'run':
                raise ValueError('simulated backup failure')
            return self.run_fake(args)
        with self.assertRaises(ValueError):
            backup_compose.backup_stack(self.base / 'host', failure)
        self.assertIn(['start', 'ft'], self.calls)
        self.assertFalse((self.base / '.compose-backup.lock').exists())

    def test_compose_stopped_service_unchanged(self):
        def stopped(args):
            return '' if args[0] == 'ps' else self.run_fake(args)
        with self.assertRaises(ValueError):
            backup_compose.backup_stack(self.base / 'host', stopped)
        self.assertFalse(any(call[0] in ('stop', 'start') for call in self.calls))

    def test_compose_stop_failure_attempts_restart(self):
        def failure(args):
            if args[0] == 'stop':
                raise ValueError('simulated stop failure')
            return self.run_fake(args)
        with self.assertRaises(ValueError):
            backup_compose.backup_stack(self.base / 'host', failure)
        self.assertIn(['start', 'ft'], self.calls)

    def test_compose_restart_failure_is_reported(self):
        def failure(args):
            if args[0] == 'start':
                raise ValueError('simulated restart failure')
            return self.run_fake(args)
        with self.assertRaisesRegex(ValueError, 'restart failure'):
            backup_compose.backup_stack(self.base / 'host', failure)
        self.assertFalse(any(call[0] == 'cp' for call in self.calls))

    def test_compose_lock_prevents_second_run(self):
        (self.base / '.compose-backup.lock').write_text('another run')
        with self.assertRaises(FileExistsError):
            backup_compose.backup_stack(self.base / 'host', self.run_fake)
        self.assertEqual(self.calls, [])

    def test_compose_corrupted_copy_not_published(self):
        def corrupted(args):
            result = self.run_fake(args)
            if args[0] == 'cp':
                (Path(args[2]) / 'secret-key.txt').write_text('corrupted')
            return result
        with self.assertRaises(ValueError):
            backup_compose.backup_stack(self.base / 'host', corrupted)
        self.assertEqual(list((self.base / 'host').iterdir()), [])
        self.assertIn(['start', 'ft'], self.calls)


if __name__ == '__main__':
    unittest.main()
