import os
from pathlib import Path
import unittest
from unittest.mock import patch

import run


class RunnerTests(unittest.TestCase):
    def test_union_does_not_double_count_nested_spans(self):
        self.assertEqual(run.union_ms([(0, 10_000_000), (2_000_000, 5_000_000),
                                      (9_000_000, 12_000_000), (20_000_000, 21_000_000)]), 13)
        self.assertEqual(run.union_ms([]), 0)

    def test_run_environment_isolates_credentials_and_engine(self):
        with patch.dict(os.environ, {'DAGGER_CLOUD_TOKEN': 'test-only',
                                    '_EXPERIMENTAL_DAGGER_RUNNER_HOST': 'unrelated',
                                    'OTEL_EXPORTER_OTLP_HEADERS': 'test-only'}, clear=True):
            env = run.environment(Path('/tmp/unit-only'), 'local:test', 'test-engine')
        self.assertNotIn('DAGGER_CLOUD_TOKEN', env)
        self.assertNotIn('_EXPERIMENTAL_DAGGER_RUNNER_HOST', env)
        self.assertNotIn('OTEL_EXPORTER_OTLP_HEADERS', env)
        self.assertEqual(env['XDG_CONFIG_HOME'], '/tmp/unit-only/cli/config')
        self.assertEqual(env['DAGGER_ENGINE'],
                         'image+docker://local:test?container=test-engine&volume=test-engine&cleanup=false')

    def test_thirteen_unique_flows(self):
        self.assertEqual(len(run.FLOWS), 13)
        self.assertEqual(len(set(run.FLOWS)), 13)
        self.assertEqual(run.FLOWS[0], 'cold')


if __name__ == '__main__':
    unittest.main()
