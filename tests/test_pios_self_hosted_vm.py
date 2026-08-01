import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from scripts import pios_self_hosted_vm as vm
from scripts import pios_google_metadata_init as metadata_init
from scripts.build_self_hosted_qemu_image_candidate import build_qemu_command
from scripts.build_self_hosted_qemu_image_candidate import (
    write_candidate_build_seed,
    write_candidate_proof_seed,
)
from scripts.prove_pios_starter_disk_image_hygiene import (
    HYGIENE_EMPTY_STATE_OK,
    HYGIENE_PROOF_DONE,
    HYGIENE_PROOF_START,
    build_hygiene_user_data,
    release_image_from_manifest,
)
from scripts.inspect_pios_starter_disk_image_residue import (
    RESIDUE_INSPECTION_PASSED,
    SEARCH_ROOTS,
    TEMPORARY_RESIDUE_PATHS,
    build_residue_inspection_user_data,
    derive_forbidden_token,
)
from scripts.clean_pios_starter_disk_image_residue import (
    CLEANUP_DONE,
    CLEANUP_START,
    TEMPORARY_MOUNT_DIRECTORY,
    build_cleanup_user_data,
)
from scripts.finalize_pios_starter_disk_image_cleanup import validate_cleanup_log
from scripts.validate_pios_starter_disk_image_evidence import validate_evidence_records
from scripts.plan_pios_starter_signing_review import build_signing_review_plan
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
            self.assertIn("docs/starter", result["copied"])
            self.assertTrue((Path(directory) / "image-root/docs/starter/README.md").is_file())

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

    def test_candidate_boot_helper_exposes_an_explicit_success_stop_marker(self) -> None:
        import inspect

        from scripts.build_self_hosted_qemu_image_candidate import boot_qemu

        self.assertIn("stop_when_seen", inspect.signature(boot_qemu).parameters)

    def test_candidate_builder_removes_temporary_offline_seed_mount_directory(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            payload = root / "payload.tar.gz"
            payload.write_bytes(b"synthetic payload")
            gvnic_dir = root / "gvnic"
            guest_agent_dir = root / "guest-agent"
            gvnic_dir.mkdir()
            guest_agent_dir.mkdir()
            (gvnic_dir / "gvnic.deb").write_bytes(b"synthetic")
            (guest_agent_dir / "guest-agent.deb").write_bytes(b"synthetic")
            seed_iso = root / "seed.iso"

            def fake_seed(*, seed_iso: Path, **_: object) -> None:
                seed_iso.write_bytes(b"synthetic seed")

            with patch(
                "scripts.build_self_hosted_qemu_image_candidate.make_seed_iso",
                side_effect=fake_seed,
            ) as make_seed, patch("scripts.build_self_hosted_qemu_image_candidate.run"):
                write_candidate_build_seed(
                    seed_dir=root / "seed",
                    seed_iso=seed_iso,
                    payload_archive=payload,
                    run_id="synthetic",
                    install_google_gvnic_modules=True,
                    google_gvnic_deb_dir=gvnic_dir,
                    install_google_guest_agent=True,
                    google_guest_agent_deb_dir=guest_agent_dir,
            )
            user_data = make_seed.call_args.kwargs["user_data"]
            self.assertIn("test ! -e /usr/sbin/policy-rc.d", user_data)
            self.assertIn("exit 101", user_data)
            self.assertIn("rm -f /usr/sbin/policy-rc.d; systemctl daemon-reload || true", user_data)
            self.assertIn("umount /mnt/pios-seed || true; rmdir /mnt/pios-seed || true", user_data)

    def test_candidate_proof_seed_runs_core_init_in_early_boothook(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            with patch("scripts.build_self_hosted_qemu_image_candidate.make_seed_iso") as make_seed:
                write_candidate_proof_seed(
                    seed_dir=root / "seed",
                    seed_iso=root / "seed.iso",
                    run_id="synthetic",
                    owner_id="owner_synthetic",
                    owner_slug="synthetic-owner",
                    env_name="proof",
                )
            user_data = make_seed.call_args.kwargs["user_data"]
            self.assertTrue(user_data.startswith("#cloud-boothook\n#!/bin/bash\n"))
            self.assertIn("/opt/pios-core/bin/pios-core-init", user_data)
            self.assertIn("sync\necho PIOS_QEMU_CANDIDATE_PROOF_DONE", user_data)

    def test_starter_hygiene_seed_requires_empty_core_state_before_init(self) -> None:
        user_data = build_hygiene_user_data(
            owner_id="owner_synthetic_owner_b",
            owner_slug="starter-hygiene-owner-b",
            env_name="starter-hygiene",
        )
        self.assertIn(HYGIENE_PROOF_START, user_data)
        self.assertIn(HYGIENE_EMPTY_STATE_OK, user_data)
        self.assertIn(HYGIENE_PROOF_DONE, user_data)
        self.assertIn("test ! -e /var/lib/pios-core", user_data)
        self.assertIn("/opt/pios-core/bin/pios-core-init", user_data)
        self.assertIn('"start_core_api": false', user_data)
        self.assertIn('"start_connectors": false', user_data)
        self.assertIn('"start_scheduler": false', user_data)
        self.assertIn("starter-hygiene-owner-b", user_data)

    def test_starter_hygiene_rejects_release_manifest_without_standalone_image(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            manifest_path = Path(directory) / "release-manifest.json"
            manifest_path.write_text(json.dumps({
                "schema_version": "self_hosted_qemu_image_release_manifest_v1",
                "status": "passed",
            }))
            with self.assertRaisesRegex(ValueError, "standalone_image"):
                release_image_from_manifest(json.loads(manifest_path.read_text()), manifest_path)

    def test_starter_residue_seed_checks_known_paths_without_embedding_token(self) -> None:
        token = "distinct-prior-synthetic-owner"
        user_data = build_residue_inspection_user_data(token)
        self.assertTrue(user_data.startswith("#cloud-boothook\n#!/bin/bash\n"))
        self.assertIn(RESIDUE_INSPECTION_PASSED, user_data)
        self.assertIn("PIOS_STARTER_RESIDUE_INSPECTION_FAILED:$search_root", user_data)
        self.assertIn("test ! -e /var/lib/pios-core", user_data)
        self.assertIn("grep -R -a -F", user_data)
        self.assertNotIn(token, user_data)
        for path in TEMPORARY_RESIDUE_PATHS:
            self.assertIn(path, user_data)
        for path in SEARCH_ROOTS:
            self.assertIn(path, user_data)
        self.assertNotIn("pios-core-init --manifest", user_data)

    def test_starter_residue_uses_source_candidate_owner_slug_by_default(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            candidate_path = Path(directory) / "candidate-result.json"
            candidate_path.write_text(json.dumps({"owner_slug": "prior-synthetic-owner"}))
            manifest_path = Path(directory) / "release-manifest.json"
            manifest = {"source_candidate_result": str(candidate_path)}
            token, source = derive_forbidden_token(manifest, manifest_path, None)
            self.assertEqual(token, "prior-synthetic-owner")
            self.assertIn("owner_slug", source)

    def test_starter_cleanup_removes_only_known_empty_temporary_mount_directory(self) -> None:
        user_data = build_cleanup_user_data()
        self.assertTrue(user_data.startswith("#cloud-boothook\n#!/bin/bash\n"))
        self.assertIn(CLEANUP_START, user_data)
        self.assertIn(CLEANUP_DONE, user_data)
        self.assertIn(f"test -d {TEMPORARY_MOUNT_DIRECTORY}", user_data)
        self.assertIn(f"rmdir {TEMPORARY_MOUNT_DIRECTORY}", user_data)
        self.assertIn(f"test ! -e {TEMPORARY_MOUNT_DIRECTORY}", user_data)
        self.assertNotIn("pios-core-init", user_data)

    def test_starter_cleanup_finalizer_requires_completed_cleanup_markers(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            log_path = Path(directory) / "cleanup.log"
            log_path.write_text(f"{CLEANUP_START}\n{CLEANUP_DONE}\n")
            markers = validate_cleanup_log(log_path)
            self.assertTrue(markers["cleanup_start_seen"])
            self.assertTrue(markers["cleanup_done_seen"])

    def test_starter_evidence_validator_requires_matching_passed_proofs(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            image = root / "starter.qcow2"
            image.write_bytes(b"synthetic")
            release_path = root / "release.json"
            release = {
                "schema_version": "self_hosted_qemu_image_release_manifest_v1",
                "status": "passed",
                "standalone_image": str(image),
                "standalone_image_sha256": "digest",
                "boot_proof": {"status": "passed"},
                "residue_cleanup": {
                    "markers": {"cleanup_start_seen": True, "cleanup_done_seen": True},
                },
            }
            hygiene = {
                "schema_version": "self_hosted_pios_starter_hygiene_proof_v1",
                "status": "passed",
                "release_manifest": str(release_path),
                "release_image": {"image": str(image), "sha256": "digest"},
                "proof": {
                    "status": "passed",
                    "markers": {
                        "proof_start_seen": True,
                        "empty_core_state_seen": True,
                        "health_schema_seen": True,
                        "health_passed_seen": True,
                        "proof_done_seen": True,
                    },
                },
            }
            residue = {
                "schema_version": "self_hosted_pios_starter_residue_inspection_v1",
                "status": "passed",
                "release_manifest": str(release_path),
                "release_image": {"image": str(image), "sha256": "digest"},
                "inspection": {
                    "status": "passed",
                    "markers": {
                        "inspection_start_seen": True,
                        "inspection_passed_seen": True,
                        "inspection_failed_seen": False,
                    },
                },
            }
            summary = validate_evidence_records(
                release_manifest=release,
                release_manifest_path=release_path,
                fresh_hygiene=hygiene,
                residue_inspection=residue,
            )
            self.assertEqual(summary["release_image_sha256"], "digest")
            residue["release_image"]["sha256"] = "different"
            with self.assertRaisesRegex(ValueError, "checksum"):
                validate_evidence_records(
                    release_manifest=release,
                    release_manifest_path=release_path,
                    fresh_hygiene=hygiene,
                    residue_inspection=residue,
                )

    def test_starter_signing_review_plan_is_explicitly_non_mutating_and_blocked(self) -> None:
        evidence = {
            "schema_version": "pios_starter_disk_image_evidence_readiness_v1",
            "status": "passed",
            "readiness": "local_image_evidence_complete",
            "release_manifest": "release.json",
            "summary": {
                "release_image": "starter.qcow2",
                "release_image_sha256": "digest",
                "package_health_proof": "passed",
                "fresh_vm_hygiene": "passed",
                "residue_inspection": "passed",
            },
        }
        plan = build_signing_review_plan(
            evidence_readiness=evidence,
            source_state={
                "commit": "abc123",
                "tags_at_head": [],
                "tracked_worktree_clean": True,
                "untracked_artifacts_intentionally_not_evaluated": True,
            },
        )
        self.assertEqual(plan["status"], "blocked_pending_owner_release_decision")
        self.assertEqual(plan["mode"], "plan_only_no_signing")
        self.assertIn("owner-approved immutable source tag", plan["missing_inputs"])
        self.assertIn("no artifact published", plan["boundaries"])

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
                user_data="synthetic-user-data.yaml",
            )
            boot = plan["commands"]["boot_retained_core_after_explicit_confirmation"]
            self.assertEqual(plan["cloud_calls"], 0)
            self.assertIn("--confirm-gcp-retained-deploy", plan["requires_confirmation_before_boot"])
            self.assertIn("--machine-type=c4a-standard-2", boot)
            self.assertIn("network=pios-core-vpc,subnet=pios-core-en1,no-address", boot)
            self.assertIn("--no-service-account", boot)
            self.assertIn("boot=yes,mode=rw,auto-delete=no", boot)
            self.assertNotIn("network=default", boot)
