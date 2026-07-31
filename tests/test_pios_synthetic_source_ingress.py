import copy
import tempfile
import unittest
from pathlib import Path

from scripts import pios_generic_source_lifecycle as lifecycle
from scripts import pios_synthetic_source_ingress as ingress


class SyntheticSourceIngressTests(unittest.TestCase):
    def source_candidate(
        self,
        *,
        record_id: str = "synthetic-item-1",
        value: str = "one",
        extensions=None,
    ):
        original = f"harmless generated C1 original:{value}\n".encode("utf-8")
        candidate = lifecycle.build_source_candidate(
            owner_id="owner_synthetic_c1",
            integration_id="synthetic-source",
            source_native_record_id=record_id,
            payload={"fixture": "generated_harmless", "value": value},
            original_bytes=original,
            processing_manifest={"fixture": "generated_harmless", "revision": 1},
            source_provenance={
                "local_capture_id": "local-only-capture",
                "manifest_path": "/private/tmp/local-only-manifest.json",
            },
            extensions={"future_extension": {"preserved": True}} if extensions is None else extensions,
        )
        return candidate, original

    def envelope(self, candidate, original, **overrides):
        values = {
            "integration_version": "1.0.0",
            "source_platform": "macos",
            "origin_device_id": "synthetic-device-1",
            "client_capture_id": "synthetic-capture-1",
            "client_item_id": "synthetic-item-1",
            "event_type": "synthetic-source.item.prepared",
            "observed_at": "2026-08-01T00:00:00Z",
            "recorded_at_local": "2026-08-01T00:00:01Z",
            "source_provenance": {
                "fixture_class": "generated_harmless",
                "source_shape": "original_byte_capture",
                "transport": "synthetic_local_projection",
            },
        }
        values.update(overrides)
        return ingress.build_synthetic_envelope(candidate, original, **values)

    def test_projection_is_deterministic_and_excludes_local_paths(self) -> None:
        candidate, original = self.source_candidate()
        first = self.envelope(candidate, original)
        second = self.envelope(candidate, original)
        self.assertEqual(first, second)
        self.assertNotIn("manifest_path", first["source_provenance"])
        self.assertEqual(
            candidate["evidence"]["source_provenance"]["manifest_path"],
            "/private/tmp/local-only-manifest.json",
        )
        self.assertNotEqual(first["candidate_integrity"], candidate["candidate_integrity"])
        self.assertEqual(ingress.validate_synthetic_envelope(first, original), first)

    def test_projection_rejects_paths_endpoints_and_non_synthetic_profile_fields(self) -> None:
        candidate, original = self.source_candidate()
        with self.assertRaises(ingress.SyntheticIngressError):
            self.envelope(
                candidate,
                original,
                source_provenance={
                    "fixture_class": "generated_harmless",
                    "source_shape": "original_byte_capture",
                    "transport": "/private/tmp/not-safe",
                },
            )
        unsafe, unsafe_original = self.source_candidate(
            extensions={"endpoint": "https://example.invalid"}
        )
        with self.assertRaises(ingress.SyntheticIngressError):
            self.envelope(unsafe, unsafe_original)
        envelope = self.envelope(candidate, original)
        envelope["profile"] = "real_profile"
        with self.assertRaises(ingress.SyntheticIngressError):
            ingress.validate_synthetic_envelope(envelope, original)

    def test_integrity_mismatches_fail_closed(self) -> None:
        candidate, original = self.source_candidate()
        envelope = self.envelope(candidate, original)
        with self.assertRaises(ingress.SyntheticIngressError):
            ingress.validate_synthetic_envelope(envelope, b"altered original")
        for field in ("candidate_integrity", "candidate_payload_integrity", "processing_manifest_integrity"):
            altered = copy.deepcopy(envelope)
            altered[field]["sha256"] = "0" * 64
            with self.assertRaises(ingress.SyntheticIngressError):
                ingress.validate_synthetic_envelope(altered, original)

    def test_accepted_duplicate_receipts_bind_every_identity_and_reference(self) -> None:
        candidate, original = self.source_candidate()
        envelope = self.envelope(candidate, original)
        with tempfile.TemporaryDirectory() as directory:
            local = ingress.LocalSyntheticSourceIngress(Path(directory) / "ingress")
            accepted = local.submit(
                envelope,
                original,
                receipt_recorded_at="2026-08-01T00:00:02Z",
            )
            self.assertEqual(accepted["status"], "accepted")
            ingress.verify_synthetic_receipt(envelope, original, accepted["receipt"])
            duplicate = local.submit(envelope, original)
            self.assertEqual(duplicate["status"], "duplicate")
            self.assertEqual(duplicate["receipt"]["receipt_id"], accepted["receipt"]["receipt_id"])
            for field, replacement in {
                "owner_id": "owner_synthetic_other",
                "origin_device_id": "synthetic-device-other",
                "client_capture_id": "synthetic-capture-other",
                "client_item_id": "synthetic-item-other",
                "source_native_record_id": "other-record",
                "stable_source_record_id": "src_" + "0" * 64,
                "idempotency_key": "idem_" + "0" * 64,
                "event_ref": "core://events/" + "0" * 64,
            }.items():
                mismatched = copy.deepcopy(accepted["receipt"])
                mismatched[field] = replacement
                with self.assertRaises(ingress.SyntheticReceiptMismatch, msg=field):
                    ingress.verify_synthetic_receipt(envelope, original, mismatched)
            provider_ref = copy.deepcopy(accepted["receipt"])
            provider_ref["original_ref"] = "s3://forbidden/bucket/object"
            with self.assertRaises(ingress.SyntheticReceiptMismatch):
                ingress.verify_synthetic_receipt(envelope, original, provider_ref)

    def test_retry_must_reuse_exact_envelope_and_revocation_blocks_new_attempts(self) -> None:
        candidate, original = self.source_candidate()
        envelope = self.envelope(candidate, original)
        changed_candidate, changed_original = self.source_candidate(value="changed")
        changed_envelope = self.envelope(changed_candidate, changed_original)
        with tempfile.TemporaryDirectory() as directory:
            local = ingress.LocalSyntheticSourceIngress(Path(directory) / "ingress")
            first = local.submit(envelope, original, test_outcome="retry_once")
            self.assertEqual(first["status"], "retry")
            with self.assertRaises(ingress.RetryBindingMismatch):
                local.submit(changed_envelope, changed_original, test_outcome="retry_once")
            accepted = local.submit(envelope, original, test_outcome="retry_once")
            self.assertEqual(accepted["status"], "accepted")
            self.assertEqual(local.revoke()["status"], "revoked")
            another_candidate, another_original = self.source_candidate(record_id="synthetic-item-2")
            another = self.envelope(another_candidate, another_original)
            self.assertEqual(local.submit(another, another_original)["code"], "grant_revoked")

    def test_export_and_independent_original_readback_are_local_only(self) -> None:
        candidate, original = self.source_candidate()
        envelope = self.envelope(candidate, original)
        with tempfile.TemporaryDirectory() as directory:
            local = ingress.LocalSyntheticSourceIngress(Path(directory) / "ingress")
            accepted = local.submit(envelope, original)
            exported = local.export()
            self.assertEqual(exported["profile"], ingress.PROFILE)
            self.assertEqual(exported["status"], "passed")
            self.assertEqual(exported["receipts"][0]["receipt_id"], accepted["receipt"]["receipt_id"])
            self.assertEqual(local.readback_original(envelope, original, accepted["receipt"]), original)


if __name__ == "__main__":
    unittest.main()
