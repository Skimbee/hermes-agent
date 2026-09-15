import importlib.util
from pathlib import Path
import unittest

spec = importlib.util.spec_from_file_location('update_diagnostics', Path(__file__).parent / 'container-e2e/update_diagnostics.py')
assert spec is not None and spec.loader is not None
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)

class DiagnosticsTests(unittest.TestCase):
    def test_poll_failure_then_success_keeps_safe_evidence(self):
        ticks = iter(range(100))
        calls = iter([TimeoutError('secret-value'), {'status': 503}, {'status': 200, 'data': {'summary': {'finished_at': 'done'}}}])
        def fetch():
            value = next(calls)
            if isinstance(value, Exception):
                raise value
            return value
        diagnostic = {}
        receipt = m.poll_receipt(fetch, diagnostic, timeout=30, clock=lambda: next(ticks), sleep=lambda _: None)
        self.assertEqual(receipt['finished_at'], 'done')
        self.assertEqual(diagnostic['attempts'], 3)
        self.assertEqual(diagnostic['last_http_status'], 200)
        self.assertEqual(diagnostic['last_error'], 'http_error')
        self.assertNotIn('secret-value', str(diagnostic))

    def test_timeout_and_log_projection_are_bounded(self):
        ticks = iter(range(100))
        diagnostic = {}
        self.assertIsNone(m.poll_receipt(lambda: {'status': 401}, diagnostic, timeout=5, clock=lambda: next(ticks), sleep=lambda _: None))
        self.assertTrue(diagnostic['timed_out'])
        output = m.log_summary('secret=private\nInstalling dependencies\nERROR password=hunter2\nbuild complete\n')
        self.assertNotIn('private', str(output))
        self.assertNotIn('hunter2', str(output))
        self.assertEqual(output['signals'], ['dependencies', 'error', 'build'])
