import copy
import tempfile
import unittest
from pathlib import Path

from scripts import pios_generic_source_lifecycle as lifecycle


class GenericSourceLifecycleTests(unittest.TestCase):
    def candidate(self, *, record_id: str = "record-1", payload_value: str = "one"):
        original = f"harmless original:{payload_value}".encode("utf-8")
        candidate = lifecycle.build_source_candidate(
            owner_id="owner_synthetic_b2",
            integration_id="synthetic-source",
            source_native_record_id=record_id,
            payload={"kind": "harmless", "value": payload_value},
            original_bytes=original,
            processing_manifest={"fixture": "generated", "revision": 1},
            source_provenance={"source_kind": "generated_fixture", "storage_locator": "opaque://local"},
            extensions={"future_extension": {"preserved": True}},
        )
        return candidate, original

    def test_accepted_duplicate_conflict_and_readback(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            store = lifecycle.LocalSyntheticSourceLifecycle(Path(directory) / "lifecycle")
            candidate, original = self.candidate()
            accepted = store.submit(candidate, original)
            self.assertEqual(accepted["status"], "accepted")
            lifecycle.verify_receipt(candidate, original, accepted["receipt"])
            self.assertEqual(store.readback_original(accepted["receipt"]), original)
            duplicate = store.submit(candidate, original)
            self.assertEqual(duplicate["status"], "duplicate")
            self.assertEqual(duplicate["receipt"], accepted["receipt"])
            changed, changed_original = self.candidate(payload_value="changed")
            conflict = store.submit(changed, changed_original)
            self.assertEqual(conflict, {"status": "denied", "code": "source_identity_conflict", "retryable": False})

    def test_denied_retry_revoked_and_export_outcomes(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            store = lifecycle.LocalSyntheticSourceLifecycle(Path(directory) / "lifecycle")
            denied, denied_original = self.candidate(record_id="denied")
            self.assertEqual(store.submit(denied, denied_original, test_outcome="deny")["code"], "synthetic_denied")
            retry, retry_original = self.candidate(record_id="retry")
            self.assertEqual(store.submit(retry, retry_original, test_outcome="retry_once")["status"], "retry")
            accepted = store.submit(retry, retry_original, test_outcome="retry_once")
            self.assertEqual(accepted["status"], "accepted")
            exported = store.export()
            self.assertEqual(exported["status"], "passed")
            self.assertEqual(exported["cursor"], 1)
            self.assertEqual(exported["receipts"][0], accepted["receipt"])
            self.assertEqual(store.revoke()["status"], "revoked")
            revoked, revoked_original = self.candidate(record_id="revoked")
            self.assertEqual(store.submit(revoked, revoked_original)["code"], "grant_revoked")

    def test_receipt_mismatch_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            store = lifecycle.LocalSyntheticSourceLifecycle(Path(directory) / "lifecycle")
            candidate, original = self.candidate()
            receipt = store.submit(candidate, original)["receipt"]
            mismatched = copy.deepcopy(receipt)
            mismatched["original_integrity"]["sha256"] = "0" * 64
            with self.assertRaises(lifecycle.ReceiptMismatch):
                lifecycle.verify_receipt(candidate, original, mismatched)

    def test_candidate_manifest_integrity_and_extensions_are_bound(self) -> None:
        candidate, original = self.candidate()
        self.assertEqual(candidate["evidence"]["extensions"], {"future_extension": {"preserved": True}})
        candidate["processing_manifest"]["revision"] = 2
        with self.assertRaises(lifecycle.LifecycleError):
            lifecycle.validate_source_candidate(candidate, original)


if __name__ == "__main__":
    unittest.main()
