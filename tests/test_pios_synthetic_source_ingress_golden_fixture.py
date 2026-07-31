import copy
import json
import tempfile
import unittest
from pathlib import Path

from scripts import pios_canonical_source_primitives as primitives
from scripts import pios_generic_source_lifecycle as lifecycle
from scripts import pios_synthetic_source_ingress as ingress


FIXTURE_ROOT = Path(__file__).parent / "fixtures" / "pios_synthetic_source_ingress_v1"


class SyntheticSourceIngressGoldenFixtureTests(unittest.TestCase):
    def artifact(self, name: str):
        return json.loads((FIXTURE_ROOT / name).read_text(encoding="utf-8"))

    def canonical_artifact(self, name: str) -> bytes:
        return primitives.canonical_json_bytes(self.artifact(name))

    def fixture_input(self):
        return copy.deepcopy(self.artifact("fixture-input.json"))

    def original(self) -> bytes:
        return (FIXTURE_ROOT / "original.bin").read_bytes()

    def source_candidate(self, values=None, original=None):
        values = self.fixture_input() if values is None else values
        original = self.original() if original is None else original
        return lifecycle.build_source_candidate(
            owner_id=values["owner_id"],
            integration_id=values["integration_id"],
            source_native_record_id=values["source_native_record_id"],
            payload=values["payload"],
            original_bytes=original,
            processing_manifest=values["processing_manifest"],
            source_provenance=values["source_provenance"],
            extensions=values["extensions"],
        )

    def envelope(self, values=None, original=None):
        values = self.fixture_input() if values is None else values
        original = self.original() if original is None else original
        c1 = dict(values["c1"])
        c1.pop("receipt_recorded_at")
        return ingress.build_synthetic_envelope(self.source_candidate(values, original), original, **c1)

    def test_checked_in_artifacts_are_exact_b1_canonical_json_values(self) -> None:
        manifest = self.artifact("golden-manifest.json")
        for name, expected_integrity in manifest["artifacts"].items():
            checked_in = (FIXTURE_ROOT / name).read_bytes()
            canonical = self.canonical_artifact(name)
            self.assertEqual(checked_in, canonical + b"\n", name)
            self.assertEqual(primitives.integrity_for_bytes(canonical), expected_integrity, name)
        original = self.original()
        self.assertEqual(primitives.integrity_for_bytes(original), manifest["original_integrity"])
        self.assertEqual(original, b"PIOS C1 harmless golden original v1.\n")

    def test_python_b1_b2_c1_output_matches_every_positive_golden_artifact(self) -> None:
        values = self.fixture_input()
        original = self.original()
        source = self.source_candidate(values, original)
        envelope = self.envelope(values, original)
        transport_candidate = ingress.LocalSyntheticSourceIngress._projected_candidate(envelope, original)
        transport_binding = {
            "schema_version": lifecycle.CANDIDATE_SCHEMA,
            "owner_id": transport_candidate["owner_id"],
            "evidence": transport_candidate["evidence"],
            "processing_manifest_integrity": transport_candidate["processing_manifest_integrity"],
        }
        envelope_binding = {
            key: value for key, value in envelope.items() if key != "envelope_integrity"
        }
        expected = {
            "fixture-input.json": values,
            "source-candidate.json": source,
            "payload.json": transport_candidate["evidence"]["payload"],
            "processing-manifest.json": transport_candidate["processing_manifest"],
            "transport-candidate-binding.json": transport_binding,
            "transport-candidate.json": transport_candidate,
            "envelope-binding.json": envelope_binding,
            "envelope.json": envelope,
        }
        with tempfile.TemporaryDirectory() as directory:
            local = ingress.LocalSyntheticSourceIngress(Path(directory) / "ingress")
            accepted = local.submit(
                envelope,
                original,
                receipt_recorded_at=values["c1"]["receipt_recorded_at"],
            )["receipt"]
            duplicate = local.submit(envelope, original)["receipt"]
            expected["accepted-receipt.json"] = accepted
            expected["duplicate-receipt.json"] = duplicate
            self.assertEqual(local.readback_original(envelope, original, accepted), original)
            self.assertEqual(ingress.verify_synthetic_receipt(envelope, original, accepted), accepted)
            self.assertEqual(ingress.verify_synthetic_receipt(envelope, original, duplicate), duplicate)
        for name, value in expected.items():
            self.assertEqual(value, self.artifact(name), name)
            self.assertEqual(primitives.canonical_json_bytes(value), self.canonical_artifact(name), name)

    def test_negative_vectors_remain_fail_closed(self) -> None:
        vectors = {vector["id"]: vector for vector in self.artifact("negative-vectors.json")["vectors"]}
        original = self.original()
        envelope = self.envelope()

        vector = vectors["altered_original_bytes"]
        with self.assertRaises(getattr(ingress, vector["expect_exception"])):
            ingress.validate_synthetic_envelope(envelope, vector["original_utf8"].encode("utf-8"))

        vector = vectors["tampered_candidate_integrity"]
        tampered = copy.deepcopy(envelope)
        tampered["candidate_integrity"]["sha256"] = vector["replacement"]
        with self.assertRaises(getattr(ingress, vector["expect_exception"])):
            ingress.validate_synthetic_envelope(tampered, original)

        vector = vectors["forbidden_extension_path"]
        unsafe = self.fixture_input()
        unsafe["extensions"].update(vector["extension_patch"])
        with self.assertRaises(getattr(ingress, vector["expect_exception"])):
            self.envelope(unsafe, original)

        vector = vectors["invalid_timestamp_precision"]
        invalid_time = self.fixture_input()
        invalid_time["c1"].update(vector["c1_patch"])
        with self.assertRaises(getattr(ingress, vector["expect_exception"])):
            self.envelope(invalid_time, original)

        vector = vectors["provider_receipt_reference"]
        receipt = copy.deepcopy(self.artifact("accepted-receipt.json"))
        receipt.update(vector["receipt_patch"])
        with self.assertRaises(getattr(ingress, vector["expect_exception"])):
            ingress.verify_synthetic_receipt(envelope, original, receipt)

        vector = vectors["changed_retry_payload"]
        changed = self.fixture_input()
        changed["payload"].update(vector["payload_patch"])
        changed_original = vector["original_utf8"].encode("utf-8")
        changed_envelope = self.envelope(changed, changed_original)
        with tempfile.TemporaryDirectory() as directory:
            local = ingress.LocalSyntheticSourceIngress(Path(directory) / "ingress")
            self.assertEqual(local.submit(envelope, original, test_outcome="retry_once")["status"], "retry")
            with self.assertRaises(getattr(ingress, vector["expect_exception"])):
                local.submit(changed_envelope, changed_original, test_outcome="retry_once")


if __name__ == "__main__":
    unittest.main()
