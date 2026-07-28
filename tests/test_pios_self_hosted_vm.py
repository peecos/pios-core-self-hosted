import json
from pathlib import Path
import tempfile
import unittest

from scripts import pios_self_hosted_vm as vm


class PiosSelfHostedVmTests(unittest.TestCase):
    def test_workspace_refuses_unmarked_content(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            workspace = Path(directory) / "workspace"
            workspace.mkdir()
            (workspace / "unrelated.txt").write_text("keep")
            with self.assertRaisesRegex(ValueError, "non-empty directory"):
                vm.ensure_workspace(workspace)

    def test_workspace_marker_allows_repeat_use(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            workspace = Path(directory) / "workspace"
            vm.ensure_workspace(workspace)
            vm.ensure_workspace(workspace)
            marker = json.loads((workspace / vm.WORKSPACE_MARKER).read_text())
            self.assertEqual(marker["schema_version"], "pios_self_hosted_vm_workspace_v1")

    def test_cleanup_requires_confirmation_and_marker(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            workspace = Path(directory) / "workspace"
            vm.ensure_workspace(workspace)
            with self.assertRaisesRegex(ValueError, "explicit confirmation"):
                vm.delete_workspace(workspace, False, "cleanup")
            result = vm.delete_workspace(workspace, True, "cleanup")
            self.assertEqual(result["status"], "removed")
            self.assertFalse(workspace.exists())

    def test_health_evidence_is_derived_from_serial_log(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            log = Path(directory) / "serial.log"
            log.write_text(
                '{"schema_version": "self_hosted_core_health_check_v1", "status": "passed"}'
            )
            self.assertEqual(vm.health_from_log(log)["status"], "passed")
            self.assertEqual(vm.health_from_log(Path(directory) / "missing.log")["status"], "not_available")

    def test_health_requires_passed_status_from_health_record(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            log = Path(directory) / "serial.log"
            log.write_text(
                '{"schema_version": "self_hosted_core_health_check_v1", "status": "failed"}\n'
                '{"schema_version": "unrelated", "status": "passed"}'
            )
            health = vm.health_from_log(log)
            self.assertEqual(health["status"], "pending_or_failed")
            self.assertEqual(health["health_record_statuses"], ["failed"])

    def test_diagnostics_reports_network_and_metadata_attempt(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            workspace = Path(directory) / "workspace"
            run_dir = workspace / "runs" / "run-1"
            run_dir.mkdir(parents=True)
            log = run_dir / "serial.log"
            log.write_text(
                'pios_google_metadata_init_result_v1 metadata_unavailable\n'
                '{"schema_version": "self_hosted_core_health_check_v1", "status": "passed"}'
            )
            record = {
                "schema_version": "pios_self_hosted_vm_run_v1",
                "image": "/tmp/base.qcow2",
                "image_sha256": "digest",
                "seed_iso": "/tmp/seed.iso",
                "overlay": str(run_dir / "overlay.qcow2"),
                "edk2_vars": str(run_dir / "vars.fd"),
                "serial_log": str(log),
                "command": ["qemu-system-aarch64", "-nic", "none"],
            }
            (run_dir / vm.RUN_RECORD).write_text(json.dumps(record))
            result = vm.diagnostics(workspace, "run-1")
            self.assertTrue(result["networking"]["qemu_nic_none"])
            self.assertTrue(result["networking"]["guest_metadata_attempt_detected"])
            self.assertEqual(result["health"]["status"], "passed")
