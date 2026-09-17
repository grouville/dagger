import unittest

import profile_windows as windows


class ProfileWindows(unittest.TestCase):
    def setUp(self):
        self.record = {'started_ns': 100, 'process_ended_ns': 1000}
        self.header = {'epoch_unix_nano': 0, 'dumped_unix_nano': 1200, 'strings': [
            'session.serveQuery', windows.HANDOFF, windows.BACKGROUND,
            'filesync.filecache.publish', 'unrelated.io']}
        self.events = [self.op(1, 0, 100, 900), self.op(2, 1, 850, 870, 1),
                       self.op(3, 2, 870, 1100), self.op(4, 3, 875, 1090, 3)]

    def op(self, ident, cls, start, stop, parent=0):
        return {'e': 'op', 'id': ident, 'c': cls, 's': start, 'd': stop, 'p': parent, 'o': 'ok'}

    def test_admission_tail_is_explicit(self):
        gates, stats = windows.validate(self.record, self.header, self.events)
        self.assertTrue(all(gates.values()), gates)
        self.assertEqual(stats['remaining_after_cli_ms'], .0001)
        self.assertEqual(stats['remaining_after_query_ms'], .0002)

    def test_unrelated_late_work_is_rejected(self):
        self.events.append(self.op(5, 4, 900, 1100))
        gates, _ = windows.validate(self.record, self.header, self.events)
        self.assertFalse(gates['foreground_inside_process_window'])

    def test_unknown_background_class_is_rejected(self):
        self.events.append(self.op(5, 4, 900, 1100, 3))
        gates, _ = windows.validate(self.record, self.header, self.events)
        self.assertFalse(gates['only_known_background_classes'])

    def test_session_parent_not_allowed(self):
        self.events[2]['p'] = 1
        gates, _ = windows.validate(self.record, self.header, self.events)
        self.assertFalse(gates['background_roots_independent'])

    def test_missing_or_open_background_cannot_pass(self):
        self.assertFalse(windows.finished(self.header, self.events[:2]))
        self.header['open_ops'] = [{'op_id': 8}]
        self.assertFalse(windows.finished(self.header, self.events))

    def test_old_or_excessive_tail_rejected(self):
        self.events[2]['s'] = 99
        gates, _ = windows.validate(self.record, self.header, self.events)
        self.assertFalse(gates['background_inside_bounded_capture_window'])
        self.events[2]['s'] = 870
        self.events[2]['d'] = windows.MAX_TAIL_NS + 1001
        gates, _ = windows.validate(self.record, self.header, self.events)
        self.assertFalse(gates['background_inside_bounded_capture_window'])

    def test_failure_is_recorded_not_hidden(self):
        self.events[2]['o'] = 'error'
        gates, stats = windows.validate(self.record, self.header, self.events)
        self.assertTrue(all(gates.values()))
        self.assertEqual(stats['background_outcomes'], ['error'])

    def test_sync_case(self):
        gates, stats = windows.validate(self.record, self.header, self.events[:1])
        self.assertTrue(all(gates.values()))
        self.assertEqual(stats['background_roots'], 0)


if __name__ == '__main__':
    unittest.main()
