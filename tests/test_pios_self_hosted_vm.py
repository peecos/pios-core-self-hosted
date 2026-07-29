import json
from pathlib import Path
import tempfile
import unittest

from scripts import pios_self_hosted_vm as vm
from scripts import pios_google_metadata_init as metadata_init
from scripts.build_self_hosted_qemu_image_candidate import build_qemu_command
from scripts.pios_local_synthetic_source import run_fixture_suite
from scripts.plan_google_cloud_import_proof import build_plan
from scripts.plan_google_cloud_retained_core import build_plan as build_retained_core_plan
from scripts.build_self_hosted_image_root import build_self_hosted_image_root


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

    def test_metadata_init_skips_local_qemu_without_network_attempt(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            dmi_root = Path(directory)
            (dmi_root / "sys_vendor").write_text("QEMU")
            (dmi_root / "product_name").write_text("Standard PC")
            called = False

            def fetcher(_: int) -> None:
                nonlocal called
                called = True

            result = metadata_init.metadata_init_result(dmi_root=dmi_root, fetcher=fetcher)
            self.assertEqual(result["status"], "skipped_not_google_compute")
            self.assertFalse(result["network_attempted"])
            self.assertFalse(called)

    def test_metadata_init_only_fetches_on_google_compute_dmi(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            dmi_root = Path(directory)
            (dmi_root / "sys_vendor").write_text("Google")
            (dmi_root / "product_name").write_text("Google Compute Engine")
            called = False

            def fetcher(_: int) -> None:
                nonlocal called
                called = True

            result = metadata_init.metadata_init_result(dmi_root=dmi_root, fetcher=fetcher)
            self.assertEqual(result["status"], "metadata_reachable")
            self.assertTrue(result["network_attempted"])
            self.assertTrue(called)

    def test_image_root_build_includes_only_present_data_empty_sources(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            result = build_self_hosted_image_root(
                output_dir=Path(directory) / "image-root",
                force=False,
                run_hygiene=True,
            )
            self.assertEqual(result["hygiene"]["status"], "passed")
            self.assertIn("scripts/pios_google_metadata_init.py", result["copied"])

    def test_candidate_qemu_command_disables_outbound_network_by_default(self) -> None:
        command = build_qemu_command(
            qemu="qemu-system-aarch64",
            code_fd="code.fd",
            vars_fd=Path("vars.fd"),
            disk_image=Path("disk.qcow2"),
            seed_iso=Path("seed.iso"),
            allow_user_network=False,
        )
        self.assertIn("-netdev", command)
        self.assertIn("user,restrict=on,id=net0", command)
        self.assertIn("virtio-net-pci,netdev=net0", command)

    def test_candidate_qemu_command_requires_explicit_opt_in_for_unrestricted_network(self) -> None:
        command = build_qemu_command(
            qemu="qemu-system-aarch64",
            code_fd="code.fd",
            vars_fd=Path("vars.fd"),
            disk_image=Path("disk.qcow2"),
            seed_iso=Path("seed.iso"),
            allow_user_network=True,
        )
        self.assertIn("user,id=net0", command)
        self.assertNotIn("user,restrict=on,id=net0", command)

    def test_synthetic_source_fixture_loop_covers_required_outcomes(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            result = run_fixture_suite(Path(directory) / "synthetic")
            fixtures = result["fixtures"]
            self.assertEqual(result["status"], "passed")
            self.assertEqual(fixtures["accepted"]["status"], "accepted")
            self.assertEqual(fixtures["duplicate"]["status"], "duplicate")
            self.assertEqual(fixtures["denied"]["status"], "denied")
            self.assertEqual(fixtures["retry_first"]["status"], "retry")
            self.assertEqual(fixtures["retry_second"]["status"], "accepted")
            self.assertEqual(fixtures["revoked_attempt"]["code"], "grant_revoked")
            self.assertEqual(fixtures["export"]["count"], 2)

    def test_gcp_planner_accepts_standalone_qcow2_manifest(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            manifest_path = Path(directory) / "release-manifest.json"
            manifest_path.write_text(json.dumps({
                "schema_version": "self_hosted_qemu_image_release_manifest_v1",
                "run_id": "synthetic-qemu",
                "standalone_image_name": "synthetic.qcow2",
                "standalone_image_sha256": "digest",
                "inspection": {"format": "qcow2"},
            }))
            plan = build_plan(
                release_manifest_path=manifest_path,
                project_id="<project>",
                region="<region>",
                zone="<zone>",
                staging_bucket="<bucket>",
                image_name="synthetic-image",
                machine_type="t2a-standard-2",
                architecture="arm64",
            )
            self.assertEqual(plan["cloud_calls"], 0)
            self.assertEqual(plan["source_artifact"]["image_name"], "synthetic.qcow2")
            self.assertEqual(plan["source_artifact"]["architecture_evidence"], "explicit_plan_argument")

    def test_retained_gcp_planner_uses_private_c4a_baseline_and_never_calls_cloud(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            archive = Path(directory) / "disk.tar.gz"
            archive.write_bytes(b"synthetic data-empty archive")
            manifest_path = Path(directory) / "artifact.json"
            manifest_path.write_text(json.dumps({
                "schema_version": "pios_google_cloud_import_artifact_v1",
                "status": "passed",
                "cloud_calls": 0,
                "archive": str(archive),
                "archive_name": archive.name,
                "archive_sha256": "digest",
            }))
            plan = build_retained_core_plan(
                artifact_manifest_path=manifest_path,
                project="pios-core-solo",
                account="valto@prifina.com",
                bucket="pios-core-solo-import-staging",
                image_name="pios-core-data-empty-arm64-v1",
                instance_name="pios-core-solo",
                zone="europe-north1-a",
                machine_type="c4a-standard-2",
                network="pios-core-vpc",
                subnet="pios-core-en1",
                boot_disk="pios-core-boot",
                core_disk="pios-core-data",
                key_disk="pios-core-keys",
                metadata_manifest="synthetic.json",
            )
            boot = plan["commands"]["boot_retained_core_after_explicit_confirmation"]
            self.assertEqual(plan["cloud_calls"], 0)
            self.assertIn("--confirm-gcp-retained-deploy", plan["requires_confirmation_before_boot"])
            self.assertIn("--machine-type=c4a-standard-2", boot)
            self.assertIn("network=pios-core-vpc,subnet=pios-core-en1,no-address", boot)
            self.assertIn("--no-service-account", boot)
            self.assertIn("boot=yes,mode=rw,auto-delete=no", boot)
            self.assertNotIn("network=default", boot)
