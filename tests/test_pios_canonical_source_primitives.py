import tempfile
import unittest
from pathlib import Path

from scripts import pios_canonical_source_primitives as primitives


class CanonicalSourcePrimitivesTests(unittest.TestCase):
    def fixture_record(self, *, payload_value: str = "first", extensions=None):
        payload = {"kind": "synthetic", "value": payload_value}
        original = f"harmless original:{payload_value}".encode("utf-8")
        stable_id = primitives.derive_stable_source_record_id("synthetic-source", "record-1")
        return primitives.build_source_evidence(
            integration_id="synthetic-source",
            source_native_record_id="record-1",
            payload=payload,
            original_bytes=original,
            logical_references={
                "event_ref": primitives.build_core_ref("events", stable_id),
                "manifest_ref": primitives.build_core_ref("system", "processing-manifests", "fixture-1"),
            },
            source_provenance={"source_kind": "generated_fixture", "storage_locator": "opaque://local"},
            extensions=extensions or {},
        ), original

    def test_canonical_json_and_derivations_are_deterministic(self) -> None:
        first = {"z": [2, {"b": True, "a": "å"}], "a": 1}
        second = {"a": 1, "z": [2, {"a": "å", "b": True}]}
        self.assertEqual(primitives.canonical_json_bytes(first), primitives.canonical_json_bytes(second))
        first_id = primitives.derive_stable_source_record_id("synthetic-source", "record-1")
        self.assertEqual(first_id, primitives.derive_stable_source_record_id("synthetic-source", "record-1"))
        integrity = primitives.integrity_for_bytes(primitives.canonical_json_bytes(first))
        self.assertEqual(
            primitives.derive_idempotency_key(first_id, integrity),
            primitives.derive_idempotency_key(first_id, integrity),
        )

    def test_same_stable_identity_with_changed_content_conflicts(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            store = primitives.LocalSyntheticEvidenceStore(Path(directory) / "synthetic-store")
            first, original = self.fixture_record(payload_value="first")
            self.assertEqual(store.retain(first, original)["status"], "accepted")
            self.assertEqual(store.retain(first, original)["status"], "duplicate")
            changed, changed_original = self.fixture_record(payload_value="changed")
            with self.assertRaises(primitives.ImmutableEvidenceConflict):
                store.retain(changed, changed_original)

    def test_unknown_extensions_survive_canonical_round_trip(self) -> None:
        extensions = {"future_source": {"opaque_flag": True, "nested": ["x", {"later": 7}]}}
        record, original = self.fixture_record(extensions=extensions)
        self.assertEqual(record["extensions"], extensions)
        with tempfile.TemporaryDirectory() as directory:
            store = primitives.LocalSyntheticEvidenceStore(Path(directory) / "synthetic-store")
            store.retain(record, original)
            self.assertEqual(store.read_evidence(record["stable_source_record_id"])["extensions"], extensions)

    def test_malformed_or_mismatched_integrity_is_rejected(self) -> None:
        with self.assertRaises(primitives.IntegrityError):
            primitives.verify_bytes(b"fixture", {"sha256": "not-a-digest", "byte_count": 7})
        expected = primitives.integrity_for_bytes(b"fixture")
        expected["byte_count"] += 1
        with self.assertRaises(primitives.IntegrityError):
            primitives.verify_bytes(b"fixture", expected)
        record, original = self.fixture_record()
        record["payload_integrity"]["sha256"] = "0" * 64
        with self.assertRaises(primitives.IntegrityError):
            primitives.LocalSyntheticEvidenceStore(Path(tempfile.gettempdir()) / "unused").retain(record, original)

    def test_noncanonical_references_and_cross_boundary_provenance_are_rejected(self) -> None:
        valid = primitives.build_core_ref("originals", "a" * 64)
        self.assertEqual(primitives.validate_core_ref(valid), valid)
        for invalid in ("s3://bucket/object", "core://events/../record", "core://events/record?x=1", "core://unknown/record"):
            with self.assertRaises(primitives.LogicalReferenceError):
                primitives.validate_core_ref(invalid)
        with self.assertRaises(primitives.LogicalReferenceError):
            primitives.validate_logical_references({"event_ref": "s3://bucket/object"})
        with self.assertRaises(primitives.LogicalReferenceError):
            primitives.validate_source_provenance({"incorrect_logical_ref": valid})


if __name__ == "__main__":
    unittest.main()
