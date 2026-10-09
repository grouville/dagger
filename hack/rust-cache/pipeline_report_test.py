import unittest

from pipeline_report import analyze


class PipelineReportTest(unittest.TestCase):
    def test_binary_waits_for_transitive_machine_code(self):
        # B starts with A's metadata and finishes before A's machine code.
        # A binary depending directly on B still has to wait for A to finish.
        plan = {"actions": [
            {"id": "a", "crate": "a", "dependencies": None, "outputs": ["a.rmeta"],
             "compiler_seconds": 10, "metadata_seconds": 2, "compiler_started_unix_nanos": 1_000_000_000},
            {"id": "b", "crate": "b", "dependencies": ["a"], "outputs": ["b.rmeta"],
             "compiler_seconds": 5, "metadata_seconds": 1, "compiler_started_unix_nanos": 3_000_000_000},
            {"id": "app", "crate": "app", "dependencies": ["b"], "outputs": ["app"],
             "compiler_seconds": 1, "compiler_started_unix_nanos": 11_000_000_000},
        ]}
        report = analyze(plan)
        self.assertEqual(report["compiler_only_paths_seconds"],
                         {"wait_for_complete_dependency": 16, "start_at_metadata": 11})
        self.assertEqual(report["observed_dependency_overlaps"],
                         [{"producer": "a", "consumer": "b", "codegen_overlap_seconds": 8,
                           "started_after_metadata": True}])

    def test_explicit_rlib_requires_machine_code(self):
        plan = {"actions": [
            {"id": "a", "crate": "a", "dependencies": [], "outputs": ["a.rmeta"],
             "compiler_seconds": 10, "metadata_seconds": 2},
            {"id": "b", "crate": "b", "dependencies": ["a"], "outputs": ["b.rmeta"],
             "args": ["--extern", "a=a.rlib"], "compiler_seconds": 5, "metadata_seconds": 1},
        ]}
        self.assertEqual(analyze(plan)["compiler_only_paths_seconds"],
                         {"wait_for_complete_dependency": 15, "start_at_metadata": 15})


if __name__ == "__main__":
    unittest.main()
