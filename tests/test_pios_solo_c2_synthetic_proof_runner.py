import ast
import contextlib
import io
import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from scripts import pios_canonical_source_primitives as primitives
from scripts import pios_generic_source_lifecycle as lifecycle
from scripts import pios_synthetic_source_ingress as ingress
from scripts import run_pios_solo_c2_synthetic_proof as c2


def sha256(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def write_canonical(path: Path, value) -> bytes:
    raw = primitives.canonical_json_bytes(value)
    path.write_bytes(raw)
    return raw


def build_fixture(root: Path) -> dict[str, str]:
    original = b"PIOS C2 harmless runner test\n"
    candidate = lifecycle.build_source_candidate(
        owner_id="owner_synthetic_corebox",
        integration_id="corebox-macos",
        source_native_record_id="corebox_item_c2_test",
        payload={"fixture": "c2_runner_test", "message": "harmless"},
        original_bytes=original,
        processing_manifest={"fixture_class": "generated_harmless", "revision": 1},
        source_provenance={"local_capture_label": "harmless-local-source"},
        extensions={"corebox": {"future_hint": "preserve-me"}},
    )
    envelope = ingress.build_synthetic_envelope(
        candidate,
        original,
        integration_version="1",
        source_platform="macos",
        origin_device_id="device_c2synthetic00000000000000000001",
        client_capture_id="capture_c2_synthetic_0001",
        client_item_id="item_c2_synthetic_0001",
        event_type="corebox.capture.item.prepared",
        observed_at="2026-08-01T00:00:00Z",
        recorded_at_local="2026-08-01T00:00:01Z",
        source_provenance={
            "fixture_class": "generated_harmless",
            "source_shape": "corebox_original_byte_capture",
            "transport": "synthetic_local_projection",
        },
    )
    (root / "original.bin").write_bytes(original)
    envelope_raw = write_canonical(root / "envelope.json", envelope)
    preview = {
        "schema_version": c2.PREVIEW_SCHEMA,
        "status": c2.FIXTURE_STATUS,
        "fixture_id": c2.FIXTURE_ID,
        "profile": c2.PROFILE,
        "owner_id": envelope["owner_id"],
        "integration_id": envelope["integration_id"],
        "origin_device_id": envelope["origin_device_id"],
        "client_capture_id": envelope["client_capture_id"],
        "client_item_id": envelope["client_item_id"],
        "original_integrity": primitives.integrity_for_bytes(original),
        "envelope_integrity": primitives.integrity_for_bytes(envelope_raw),
        "app_networking": False,
        "c2_execution": False,
        "device_enrollment": False,
        "real_personal_file_intake": False,
        "network_calls": 0,
        "cloud_calls": 0,
    }
    preview_raw = write_canonical(root / "corebox-c2-zero-write-preview.json", preview)
    manifest = {
        "schema_version": c2.FIXTURE_SCHEMA,
        "fixture_id": c2.FIXTURE_ID,
        "source": c2.FIXTURE_SOURCE,
        "profile": c2.PROFILE,
        "status": c2.FIXTURE_STATUS,
        "authorization": c2.EXPECTED_AUTHORIZATION,
        "expected_lifecycle_checks": c2.EXPECTED_LIFECYCLE_CHECKS,
        "artifacts": {
            "original.bin": primitives.integrity_for_bytes(original),
            "envelope.json": primitives.integrity_for_bytes(envelope_raw),
            "corebox-c2-zero-write-preview.json": primitives.integrity_for_bytes(preview_raw),
        },
    }
    manifest_raw = write_canonical(root / "fixture-manifest.json", manifest)
    return {
        "original": sha256(original),
        "envelope": sha256(envelope_raw),
        "preview": sha256(preview_raw),
        "manifest": sha256(manifest_raw),
    }


class C2SyntheticProofRunnerTests(unittest.TestCase):
    def preview(self, root: Path, hashes: dict[str, str], **kwargs):
        return c2.run_zero_write_preview(
            input_dir=root,
            expected_original_sha256=hashes["original"],
            expected_envelope_sha256=hashes["envelope"],
            expected_zero_write_preview_sha256=hashes["preview"],
            expected_fixture_manifest_sha256=hashes["manifest"],
            **kwargs,
        )

    def test_preview_verifies_fixture_without_creating_lifecycle_or_evidence(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "fixture"
            root.mkdir()
            hashes = build_fixture(root)
            before = {path.name: path.read_bytes() for path in root.iterdir()}
            preview = self.preview(
                root,
                hashes,
                proof_id="c2-runner-test-r1",
                receipt_recorded_at="2026-08-01T00:00:02Z",
            )
            self.assertEqual(preview["status"], c2.FIXTURE_STATUS)
            self.assertFalse(preview["execution_authorized"])
            self.assertFalse(preview["lifecycle_submission_performed"])
            self.assertFalse(preview["writes_performed"])
            self.assertEqual(preview["checks"]["c1_envelope_validation"], "passed")
            self.assertEqual({path.name: path.read_bytes() for path in root.iterdir()}, before)
            self.assertEqual({path.name for path in root.iterdir()}, c2.REQUIRED_FILES)

    def test_preview_rejects_tampered_original_before_lifecycle_use(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "fixture"
            root.mkdir()
            hashes = build_fixture(root)
            (root / "original.bin").write_bytes(b"tampered")
            with self.assertRaises(c2.C2PreviewError):
                self.preview(root, hashes)

    def test_confirmation_flag_refuses_execution_without_reading_or_writing_fixture(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "fixture"
            root.mkdir()
            hashes = build_fixture(root)
            arguments = [
                "--input-dir", str(root),
                "--expected-original-sha256", hashes["original"],
                "--expected-envelope-sha256", hashes["envelope"],
                "--expected-zero-write-preview-sha256", hashes["preview"],
                "--expected-fixture-manifest-sha256", hashes["manifest"],
                "--confirm-c2-local-synthetic-proof",
            ]
            before = {path.name: path.read_bytes() for path in root.iterdir()}
            with contextlib.redirect_stderr(io.StringIO()):
                self.assertEqual(c2.main(arguments), 2)
            self.assertEqual({path.name: path.read_bytes() for path in root.iterdir()}, before)

    def test_runner_does_not_import_network_or_process_modules(self) -> None:
        source = Path(c2.__file__).read_text(encoding="utf-8")
        imports = set()
        for node in ast.walk(ast.parse(source)):
            if isinstance(node, ast.Import):
                imports.update(alias.name.split(".")[0] for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imports.add(node.module.split(".")[0])
        self.assertTrue({"socket", "subprocess", "urllib", "http", "requests"}.isdisjoint(imports))


if __name__ == "__main__":
    unittest.main()
