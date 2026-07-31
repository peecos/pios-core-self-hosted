import copy
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from scripts import pios_generic_source_lifecycle as lifecycle
from scripts import pios_projection_approval_primitives as primitives


NOW = datetime(2026, 7, 31, 15, 30, 0, tzinfo=timezone.utc)


class ProjectionApprovalPrimitiveTests(unittest.TestCase):
    def accepted_receipt(self):
        candidate = lifecycle.build_source_candidate(
            owner_id="owner_synthetic_b4",
            integration_id="synthetic-projection-source",
            source_native_record_id="generated-source-1",
            payload={"fixture": "generated_harmless", "revision": 1},
            original_bytes=b"harmless generated original",
            processing_manifest={"fixture": "generated_harmless", "stage": "projection"},
            source_provenance={"fixture_class": "generated_harmless", "transport": "local_only"},
            extensions={"unknown_extension": {"preserve": True}},
        )
        with tempfile.TemporaryDirectory() as directory:
            store = lifecycle.LocalSyntheticSourceLifecycle(Path(directory) / "source")
            result = store.submit(candidate, b"harmless generated original")
            return copy.deepcopy(result["receipt"])

    def challenge(self, *, action_type="export_projection", issued_at=NOW):
        return primitives.begin_sensitive_action(
            owner_id="owner_synthetic_b4",
            action_type=action_type,
            parameters={"fixture": "generated_harmless", "scope": "one_projection"},
            session_binding="binding_synthetic_session",
            csrf_binding="binding_synthetic_csrf",
            issued_at=issued_at,
        )

    def test_projection_is_a_separate_immutable_view_of_receipt_truth(self) -> None:
        receipt = self.accepted_receipt()
        original_receipt = copy.deepcopy(receipt)
        projection = primitives.build_projection_record(
            source_receipt=receipt,
            projection_fields={"label": "harmless generated projection"},
            extensions={"future_projection_field": {"keep": "yes"}},
        )
        self.assertEqual(primitives.validate_projection_record(projection), projection)
        self.assertEqual(receipt, original_receipt)
        projection["projection_fields"]["label"] = "changed view only"
        self.assertEqual(receipt, original_receipt)
        with self.assertRaises(primitives.ProjectionApprovalError):
            primitives.validate_projection_record(projection)

    def test_action_classification_requires_explicit_sensitive_policy(self) -> None:
        self.assertEqual(primitives.classify_action("view_projection"), primitives.READ_ONLY)
        self.assertEqual(primitives.classify_action("export_projection"), primitives.SENSITIVE)
        with self.assertRaises(primitives.ProjectionApprovalError):
            primitives.classify_action("unclassified_action")
        with self.assertRaises(primitives.ProjectionApprovalError):
            self.challenge(action_type="view_projection")

    def test_action_bound_proof_persists_immutable_audit_before_approval(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            audit_store = primitives.LocalImmutableAuditStore(Path(directory) / "audit-store")
            harness = primitives.LocalSyntheticApprovalHarness(audit_store)
            challenge = self.challenge()
            proof = primitives.build_synthetic_approval_proof(challenge=challenge, approved_at=NOW)
            outcome = harness.approve(challenge=challenge, proof=proof, now=NOW)
            self.assertEqual(outcome["status"], "approved")
            self.assertTrue(audit_store.has_audit(outcome["audit_id"]))
            self.assertTrue(outcome["approval_ref"].startswith("core://system/approvals/"))
            self.assertTrue(outcome["audit_ref"].startswith("core://system/audit/"))

    def test_expired_and_replayed_proofs_fail_closed(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            audit_store = primitives.LocalImmutableAuditStore(Path(directory) / "audit-store")
            harness = primitives.LocalSyntheticApprovalHarness(audit_store)
            expired = self.challenge()
            expired_proof = primitives.build_synthetic_approval_proof(
                challenge=expired, approved_at=NOW
            )
            with self.assertRaisesRegex(primitives.ApprovalRejected, "approval_expired"):
                harness.approve(
                    challenge=expired,
                    proof=expired_proof,
                    now=NOW + timedelta(seconds=301),
                )
            challenge = self.challenge(issued_at=NOW + timedelta(seconds=1))
            proof = primitives.build_synthetic_approval_proof(
                challenge=challenge, approved_at=NOW + timedelta(seconds=1)
            )
            harness.approve(challenge=challenge, proof=proof, now=NOW + timedelta(seconds=1))
            with self.assertRaisesRegex(primitives.ApprovalRejected, "approval_replayed"):
                harness.approve(challenge=challenge, proof=proof, now=NOW + timedelta(seconds=1))

    def test_audit_write_failure_does_not_consume_proof_or_action(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "audit-store"
            challenge = self.challenge()
            proof = primitives.build_synthetic_approval_proof(challenge=challenge, approved_at=NOW)
            failing = primitives.LocalSyntheticApprovalHarness(
                primitives.LocalImmutableAuditStore(root, fail_writes=True)
            )
            with self.assertRaisesRegex(primitives.AuditPersistenceError, "synthetic_audit_write_failure"):
                failing.approve(challenge=challenge, proof=proof, now=NOW)
            good_store = primitives.LocalImmutableAuditStore(root)
            self.assertFalse(good_store.has_action(challenge["action_id"]))
            accepted = primitives.LocalSyntheticApprovalHarness(good_store).approve(
                challenge=challenge, proof=proof, now=NOW
            )
            self.assertTrue(good_store.has_audit(accepted["audit_id"]))

    def test_proof_with_changed_csrf_binding_is_rejected(self) -> None:
        challenge = self.challenge()
        proof = primitives.build_synthetic_approval_proof(challenge=challenge, approved_at=NOW)
        changed = copy.deepcopy(proof)
        changed["csrf_binding"] = "binding_other_csrf"
        with self.assertRaises(primitives.ApprovalRejected):
            primitives.validate_approval_proof(challenge=challenge, proof=changed, now=NOW)

    def test_module_has_no_network_transport_client_imports(self) -> None:
        source = Path(primitives.__file__).read_text()
        for forbidden in (
            "import socket",
            "import urllib",
            "import requests",
            "import http",
            "import subprocess",
        ):
            self.assertNotIn(forbidden, source)


if __name__ == "__main__":
    unittest.main()
