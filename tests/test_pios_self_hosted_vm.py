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
            log.write_text("\n".join(vm.HEALTH_MARKERS))
            self.assertEqual(vm.health_from_log(log)["status"], "passed")
            self.assertEqual(vm.health_from_log(Path(directory) / "missing.log")["status"], "not_available")
