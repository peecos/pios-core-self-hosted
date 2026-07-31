import tempfile
import unittest
from pathlib import Path

from scripts import pios_canonical_source_primitives as primitives
from scripts import pios_generic_source_lifecycle as lifecycle
from scripts import pios_source_adapter_templates as adapters


class SourceAdapterTemplateTests(unittest.TestCase):
    def test_original_byte_template_is_harmless_and_conforms_to_lifecycle(self) -> None:
        prepared = adapters.OriginalByteCaptureTemplate().prepare_generated(
            source_native_record_id="generated-item-1",
            extensions={"future_extension": {"round_trip": "yes"}},
        )
        self.assertEqual(prepared.template_name, "original_byte_capture")
        self.assertTrue(prepared.original_bytes.startswith(b"PIOS Starter harmless"))
        self.assertEqual(
            prepared.candidate["evidence"]["extensions"],
            {"future_extension": {"round_trip": "yes"}},
        )
        normalized = lifecycle.validate_source_candidate(prepared.candidate, prepared.original_bytes)
        self.assertEqual(normalized["evidence"]["integration_id"], "original-byte-capture")

    def test_structured_evidence_template_uses_canonical_generated_bytes(self) -> None:
        prepared = adapters.StructuredEvidenceTemplate().prepare_generated(
            source_native_record_id="generated-record-1",
            extensions={"unknown_shape": {"keep": True}},
        )
        self.assertEqual(prepared.template_name, "structured_evidence")
        self.assertEqual(
            prepared.original_bytes,
            b'{"fixture":"generated_harmless","record_kind":"structured_evidence","version":1}',
        )
        self.assertEqual(
            prepared.candidate["evidence"]["extensions"],
            {"unknown_shape": {"keep": True}},
        )
        lifecycle.validate_source_candidate(prepared.candidate, prepared.original_bytes)

    def test_local_outbox_and_receipt_ledger_are_immutable_and_idempotent(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            harness = adapters.LocalSyntheticAdapterHarness(Path(directory) / "harness")
            prepared = adapters.OriginalByteCaptureTemplate().prepare_generated(
                source_native_record_id="generated-item-2"
            )
            outbox = harness.enqueue(prepared)
            stable_id = outbox["candidate"]["evidence"]["stable_source_record_id"]
            reread = harness.read_outbox(stable_id)
            self.assertEqual(reread, outbox)
            accepted = harness.submit_enqueued(stable_id)
            self.assertEqual(accepted["status"], "accepted")
            duplicate = harness.submit_enqueued(stable_id)
            self.assertEqual(duplicate, {"status": "duplicate", "receipt": accepted["receipt"]})
            ledger = harness.read_receipt_ledger(accepted["receipt"]["receipt_id"])
            self.assertEqual(ledger["receipt"], accepted["receipt"])
            self.assertEqual(ledger["candidate_integrity"], outbox["candidate"]["candidate_integrity"])
            self.assertEqual(harness.lifecycle.readback_original(accepted["receipt"]), prepared.original_bytes)

    def test_template_harness_remains_local_and_rejects_tampered_outbox_bytes(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "harness"
            harness = adapters.LocalSyntheticAdapterHarness(root)
            prepared = adapters.StructuredEvidenceTemplate().prepare_generated(
                source_native_record_id="generated-record-2"
            )
            outbox = harness.enqueue(prepared)
            stable_id = outbox["candidate"]["evidence"]["stable_source_record_id"]
            digest = outbox["original_integrity"]["sha256"]
            original_path = root / "outbox-originals" / f"{digest}.bin"
            original_path.write_bytes(b"tampered")
            with self.assertRaises(primitives.IntegrityError) as rejected:
                harness.submit_enqueued(stable_id)
            self.assertIn("integrity mismatch", str(rejected.exception))

    def test_harness_rejects_noncanonical_receipt_paths(self) -> None:
        harness = adapters.LocalSyntheticAdapterHarness(Path("/private/tmp/pios-b3-path-test"))
        with self.assertRaises(adapters.AdapterTemplateError):
            harness.read_receipt_ledger("rcpt_../../not-a-receipt")


if __name__ == "__main__":
    unittest.main()
