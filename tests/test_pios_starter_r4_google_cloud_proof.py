import hashlib
import json
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from scripts import plan_pios_starter_r4_google_cloud_proof as planner
from scripts import run_pios_starter_r4_google_cloud_proof as runner


class R4GoogleCloudProofTests(unittest.TestCase):
    def artifact_manifest(self, root: Path, proof_id: str = "r4-20260731-preview") -> Path:
        archive = root / "disk.tar.gz"
        archive.write_bytes(b"generated local archive")
        manifest = {
            "schema_version": planner.ARTIFACT_SCHEMA,
            "status": "passed",
            "cloud_calls": 0,
            "provider": "google_cloud",
            "r4_qcow2_sha256": planner.R4_QCOW2_SHA256,
            "archive": str(archive),
            "archive_sha256": hashlib.sha256(archive.read_bytes()).hexdigest(),
            "raw_image_sha256": "a" * 64,
            "archive_listing": ["disk.raw"],
            "temporary_resources": planner.temporary_names(proof_id),
        }
        path = root / "artifact.json"
        path.write_text(json.dumps(manifest))
        return path

    def test_temporary_names_are_isolated_and_never_persistent(self) -> None:
        names = planner.temporary_names("r4-20260731-review-a1")
        self.assertTrue(all(value.startswith(planner.TEMPORARY_PREFIX) for key, value in names.items() if key != "output_directory"))
        self.assertNotIn("pios-core-solo", json.dumps(names))
        with self.assertRaises(planner.R4ProofPlanError):
            planner.validate_proof_id("pios-core-solo")
        with self.assertRaises(planner.R4ProofPlanError):
            planner.validate_proof_id("r4-20260731-preview", executable=True)

    def test_synthetic_first_boot_manifest_keeps_all_gates_false(self) -> None:
        manifest = planner.build_synthetic_first_boot_manifest("r4-20260731-review-a1")
        planner.assert_all_gates_false(manifest)
        self.assertTrue(manifest["core_instance"]["owner_id"].startswith("owner_synthetic_"))
        user_data = planner.build_cloud_init_user_data("r4-20260731-review-a1")
        self.assertTrue(user_data.startswith("#cloud-config\n"))
        self.assertIn("PIOS_R4_GCP_PROOF_DONE", user_data)
        self.assertIn('"start_core_api": false', user_data)
        self.assertNotIn("pios-self-hosted-manifest=", user_data)

    def test_execution_commands_match_private_c4a_hyperdisk_uefi_baseline(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            archive = Path(directory) / "archive.tar.gz"
            archive.write_bytes(b"archive")
            commands = planner.build_execution_commands(
                project="pios-core-solo",
                account="operator@example.invalid",
                billing_account="000000-000000-000000",
                network="pios-core-vpc",
                subnet="pios-core-en1",
                proof_id="r4-20260731-review-a1",
                artifact_manifest={"archive": archive},
                user_data_path=Path(directory) / "user-data.yaml",
            )
        image = commands["create_image"]
        instance = commands["create_instance"]
        self.assertIn("--guest-os-features=GVNIC,UEFI_COMPATIBLE", image)
        self.assertIn("--type=hyperdisk-balanced", commands["create_boot_disk"])
        self.assertIn("--type=hyperdisk-balanced", commands["create_core_disk"])
        self.assertIn("--machine-type=c4a-standard-2", instance)
        self.assertIn("--network-interface=network=pios-core-vpc,subnet=pios-core-en1,no-address,nic-type=GVNIC", instance)
        self.assertIn("--shielded-secure-boot", instance)
        self.assertIn("--shielded-vtpm", instance)
        self.assertIn("--shielded-integrity-monitoring", instance)
        self.assertIn("--no-service-account", instance)
        self.assertIn("--no-scopes", instance)
        self.assertIn("--metadata-from-file=user-data=", " ".join(instance))
        self.assertNotIn("pd-balanced", json.dumps(commands))
        self.assertNotIn("network=default", json.dumps(commands))

    def test_preview_is_zero_cloud_call_even_when_runner_is_available(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            artifact = self.artifact_manifest(root)
            with patch("scripts.run_pios_starter_r4_google_cloud_proof.run_command", side_effect=AssertionError):
                result = runner.preview_or_run(
                    artifact_manifest_path=artifact,
                    output_dir=root / "output",
                    proof_id="r4-20260731-preview",
                    project="pios-core-solo",
                    account="operator@example.invalid",
                    billing_account="<owner-approved-billing-account>",
                    budget_display_name="<owner-approved-r4-proof-budget-name>",
                    network="pios-core-vpc",
                    subnet="pios-core-en1",
                    monthly_cost_ceiling_usd=0,
                    proof_cost_ceiling_usd=0,
                    confirm=False,
                    timeout_seconds=1,
                    poll_seconds=1,
                )
            self.assertEqual(result["status"], "preview_only")
            self.assertEqual(result["cloud_calls"], 0)
            self.assertIn(planner.CONFIRMATION_FLAG, result["requires_confirmation"])
            self.assertTrue((root / "output/r4-gcp-proof-preview.json").is_file())

    def test_execution_requires_real_unique_id_billing_and_positive_limits_before_cloud_call(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            artifact = self.artifact_manifest(root)
            with patch("scripts.run_pios_starter_r4_google_cloud_proof.run_command", side_effect=AssertionError):
                with self.assertRaises(runner.R4ProofExecutionError):
                    runner.preview_or_run(
                        artifact_manifest_path=artifact,
                        output_dir=root / "output",
                        proof_id="r4-20260731-preview",
                        project="pios-core-solo",
                        account="operator@example.invalid",
                        billing_account="<owner-approved-billing-account>",
                        budget_display_name="<owner-approved-r4-proof-budget-name>",
                        network="pios-core-vpc",
                        subnet="pios-core-en1",
                        monthly_cost_ceiling_usd=0,
                        proof_cost_ceiling_usd=0,
                        confirm=True,
                        timeout_seconds=1,
                        poll_seconds=1,
                    )

    def test_iap_firewall_and_health_parsers_fail_closed(self) -> None:
        allowed = [{"sourceRanges": [planner.IAP_TCP_SOURCE_RANGE], "allowed": [{"IPProtocol": "tcp", "ports": ["22"]}]}]
        self.assertTrue(runner.firewall_allows_iap_ssh(allowed))
        self.assertFalse(runner.firewall_allows_iap_ssh([]))
        health = {
            "schema_version": runner.HEALTH_SCHEMA,
            "status": "passed",
            "zones": {name: {"exists": True} for name in ("originals", "events", "knowledge", "derived", "system")},
        }
        self.assertEqual(runner.validate_iap_health_readback(json.dumps(health))["status"], "passed")
        health["zones"]["system"]["exists"] = False
        with self.assertRaises(runner.R4ProofExecutionError):
            runner.validate_iap_health_readback(json.dumps(health))

    def test_execution_failure_still_records_cleanup_evidence(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            artifact = self.artifact_manifest(root, "r4-20260731-review-a1")
            cleanup = [{"step": "delete_instance", "returncode": 0, "stdout": "", "stderr": ""}]
            with patch(
                "scripts.run_pios_starter_r4_google_cloud_proof.run_preflight", return_value={"cloud_call_count": 15}
            ), patch(
                "scripts.run_pios_starter_r4_google_cloud_proof.run_command",
                side_effect=runner.R4ProofExecutionError("quota blocked"),
            ), patch("scripts.run_pios_starter_r4_google_cloud_proof.cleanup", return_value=cleanup):
                result = runner.preview_or_run(
                    artifact_manifest_path=artifact,
                    output_dir=root / "output",
                    proof_id="r4-20260731-review-a1",
                    project="pios-core-solo",
                    account="operator@example.invalid",
                    billing_account="000000-000000-000000",
                    budget_display_name="PIOS r4 proof ceiling",
                    network="pios-core-vpc",
                    subnet="pios-core-en1",
                    monthly_cost_ceiling_usd=200,
                    proof_cost_ceiling_usd=10,
                    confirm=True,
                    timeout_seconds=1,
                    poll_seconds=1,
                )
            self.assertEqual(result["status"], "failed")
            self.assertIn("quota blocked", result["failure"])
            self.assertEqual(result["cleanup_status"], "complete")
            self.assertTrue((root / "output/r4-gcp-proof-result.json").is_file())

    def test_early_preflight_failure_does_not_delete_unverified_names(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            artifact = self.artifact_manifest(root, "r4-20260731-review-a1")
            with patch(
                "scripts.run_pios_starter_r4_google_cloud_proof.run_preflight",
                side_effect=runner.R4ProofExecutionError("billing blocked"),
            ), patch("scripts.run_pios_starter_r4_google_cloud_proof.cleanup", side_effect=AssertionError):
                result = runner.preview_or_run(
                    artifact_manifest_path=artifact,
                    output_dir=root / "output",
                    proof_id="r4-20260731-review-a1",
                    project="pios-core-solo",
                    account="operator@example.invalid",
                    billing_account="000000-000000-000000",
                    budget_display_name="PIOS r4 proof ceiling",
                    network="pios-core-vpc",
                    subnet="pios-core-en1",
                    monthly_cost_ceiling_usd=200,
                    proof_cost_ceiling_usd=10,
                    confirm=True,
                    timeout_seconds=1,
                    poll_seconds=1,
                )
            self.assertEqual(result["cleanup_status"], "not_required_preflight_failed")
            self.assertIn("billing blocked", result["failure"])

    def test_serial_markers_require_five_zone_health_success(self) -> None:
        passed = (
            f"{runner.PROOF_START}\n{runner.PROOF_HEALTH}\n{runner.PROOF_DONE}\n"
            f'"schema_version": "{runner.HEALTH_SCHEMA}"\n"status": "passed"'
        )
        self.assertTrue(runner.serial_proof_passed(passed))
        self.assertFalse(runner.serial_proof_passed(runner.PROOF_DONE))

    def test_artifact_checksum_mismatch_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            artifact = self.artifact_manifest(root)
            value = json.loads(artifact.read_text())
            value["archive_sha256"] = "0" * 64
            artifact.write_text(json.dumps(value))
            with self.assertRaises(runner.R4ProofExecutionError):
                runner.load_r4_artifact(artifact)

    def test_billing_linkage_and_budget_posture_are_parsed_and_fail_closed(self) -> None:
        active = runner.validate_active_account(
            [{"account": "operator@example.invalid", "status": "ACTIVE"}], account="operator@example.invalid"
        )
        self.assertEqual(active["status"], "ACTIVE")
        project = runner.validate_project_identity(
            {"projectId": "pios-core-solo", "projectNumber": "123456789012", "lifecycleState": "ACTIVE"},
            project="pios-core-solo",
        )
        billing = runner.validate_billing_linkage(
            {"billingAccountName": "billingAccounts/000000-000000-000000"},
            billing_account="000000-000000-000000",
        )
        self.assertTrue(billing["billing_enabled"])
        budget = {
            "displayName": "PIOS r4 proof ceiling",
            "budgetFilter": {"projects": [f"projects/{project['project_number']}"]},
            "amount": {"specifiedAmount": {"currencyCode": "USD", "units": "200", "nanos": 0}},
            "thresholdRules": [
                {"thresholdPercent": 0.5},
                {"thresholdPercent": "0.8"},
                {"thresholdPercent": 1.0},
            ],
            "notificationsRule": {},
        }
        posture = runner.validate_budget_posture(
            [budget],
            project="pios-core-solo",
            project_number=project["project_number"],
            budget_display_name="PIOS r4 proof ceiling",
            monthly_cost_ceiling_usd=200,
        )
        self.assertEqual(posture["amount_usd"], "200")
        self.assertEqual(posture["alert_delivery_mode"], "default_iam_recipients")
        with self.assertRaisesRegex(runner.R4ProofExecutionError, "not linked"):
            runner.validate_billing_linkage(
                {"billingAccountName": "billingAccounts/999999-999999-999999"},
                billing_account="000000-000000-000000",
            )
        with self.assertRaisesRegex(runner.R4ProofExecutionError, "budget is absent"):
            runner.validate_budget_posture(
                [],
                project="pios-core-solo",
                project_number=project["project_number"],
                budget_display_name="PIOS r4 proof ceiling",
                monthly_cost_ceiling_usd=200,
            )
        with self.assertRaisesRegex(runner.R4ProofExecutionError, "threshold"):
            runner.validate_budget_posture(
                [{**budget, "thresholdRules": [{"thresholdPercent": 1.0}]}],
                project="pios-core-solo",
                project_number=project["project_number"],
                budget_display_name="PIOS r4 proof ceiling",
                monthly_cost_ceiling_usd=200,
            )

    def test_preflight_failure_preserves_partial_read_only_evidence(self) -> None:
        commands = {
            name: [name]
            for name in (
                "verify_active_account",
                "verify_project",
                "verify_billing",
                "verify_budget_visibility",
            )
        }
        responses = [
            subprocess.CompletedProcess([], 0, json.dumps([{"account": "operator@example.invalid", "status": "ACTIVE"}]), ""),
            subprocess.CompletedProcess([], 0, json.dumps({"projectId": "pios-core-solo", "projectNumber": "123456789012"}), ""),
            subprocess.CompletedProcess([], 0, json.dumps({"billingAccountName": "billingAccounts/000000-000000-000000"}), ""),
            subprocess.CompletedProcess([], 0, json.dumps([]), ""),
        ]
        with patch("scripts.run_pios_starter_r4_google_cloud_proof.run_command", side_effect=responses):
            with self.assertRaises(runner.R4ProofPreflightError) as raised:
                runner.run_preflight(
                    commands,
                    project="pios-core-solo",
                    account="operator@example.invalid",
                    billing_account="000000-000000-000000",
                    budget_display_name="PIOS r4 proof ceiling",
                    monthly_cost_ceiling_usd=200,
                )
        self.assertEqual(raised.exception.results["cloud_call_count"], 4)
        self.assertIn("verify_budget_visibility", raised.exception.results)

    def test_confirmed_execution_uses_isolated_lifecycle_instead_of_iam_introspection(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            artifact = self.artifact_manifest(root, "r4-20260731-review-a1")
            cleanup = [{"step": "delete_instance", "returncode": 0, "stdout": "", "stderr": ""}]
            with patch(
                "scripts.run_pios_starter_r4_google_cloud_proof.run_preflight", return_value={"cloud_call_count": 15}
            ), patch(
                "scripts.run_pios_starter_r4_google_cloud_proof.run_command",
                side_effect=runner.R4ProofExecutionError("create blocked"),
            ), patch("scripts.run_pios_starter_r4_google_cloud_proof.cleanup", return_value=cleanup):
                result = runner.preview_or_run(
                    artifact_manifest_path=artifact,
                    output_dir=root / "output",
                    proof_id="r4-20260731-review-a1",
                    project="pios-core-solo",
                    account="operator@example.invalid",
                    billing_account="000000-000000-000000",
                    budget_display_name="PIOS r4 proof ceiling",
                    network="pios-core-vpc",
                    subnet="pios-core-en1",
                    monthly_cost_ceiling_usd=200,
                    proof_cost_ceiling_usd=10,
                    confirm=True,
                    timeout_seconds=1,
                    poll_seconds=1,
                )
            self.assertEqual(result["effective_permission_validation"]["mode"], "isolated_full_lifecycle")
            self.assertEqual(result["effective_permission_validation"]["status"], "failed")


if __name__ == "__main__":
    unittest.main()
