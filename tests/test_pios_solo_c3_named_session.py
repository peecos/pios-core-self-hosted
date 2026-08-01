import ast
import contextlib
import io
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from scripts import pios_c3_local_transport as transport
from scripts import run_pios_solo_c2_synthetic_proof as c2
from scripts import run_pios_solo_c3_named_session as c3_session


class C3NamedSessionPreviewTests(unittest.TestCase):
    def fixture_directory(self, root: Path) -> Path:
        fixture = root / "fixture"
        fixture.mkdir()
        for name in c3_session.FIXTURE_FILE_NAMES:
            (fixture / name).write_bytes(b"harmless test placeholder")
        return fixture

    def c1_preview(self) -> dict:
        return {
            "fixture": {
                "fixture_id": transport.FIXTURE_ID,
                "source": c2.FIXTURE_SOURCE,
                "profile": c2.PROFILE,
                "fixture_manifest_integrity": transport.fixed_c2_fixture_integrities()["fixture_manifest"],
                "artifacts": transport.fixed_c2_fixture_integrities(),
            },
            "checks": {"c1_envelope_validation": "passed"},
        }

    def test_preview_binds_review_vector_and_plans_no_session(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            fixture = self.fixture_directory(Path(directory))
            before = {path.name: path.read_bytes() for path in fixture.iterdir()}
            with mock.patch.object(c3_session.c2, "run_zero_write_preview", return_value=self.c1_preview()) as c1:
                preview = c3_session.run_zero_write_preview(input_dir=fixture)
            fixed = transport.fixed_c2_fixture_integrities()
            c1.assert_called_once_with(
                input_dir=fixture,
                expected_original_sha256=fixed["original"]["sha256"],
                expected_envelope_sha256=fixed["envelope"]["sha256"],
                expected_zero_write_preview_sha256=fixed["zero_write_preview"]["sha256"],
                expected_fixture_manifest_sha256=fixed["fixture_manifest"]["sha256"],
            )
            self.assertEqual(preview["status"], "preview_refusal_only")
            self.assertEqual(preview["revisions"], {"solo_foundation_commit": "45c5bac", "corebox_contract_commit": "1db18d5"})
            self.assertEqual(preview["review_vector"]["request_integrity"]["sha256"], c3_session.REVIEW_REQUEST_SHA256)
            self.assertEqual(preview["review_vector"]["frame_byte_count"], 1094)
            self.assertEqual(preview["review_vector"]["semantic_request_id"], c3_session.REVIEW_SEMANTIC_REQUEST_ID)
            self.assertEqual(preview["review_vector"]["connection_binding_hash"], c3_session.REVIEW_CONNECTION_BINDING_HASH)
            self.assertFalse(preview["socket_session_executed"])
            self.assertFalse(preview["fixture_submission_performed"])
            self.assertFalse(preview["lifecycle_execution_performed"])
            self.assertFalse(preview["writes_performed"])
            self.assertEqual(preview["network_or_cloud_calls"], 0)
            self.assertEqual({path.name: path.read_bytes() for path in fixture.iterdir()}, before)

    def test_preview_refuses_symlink_or_unreviewed_fixture_path_before_c1(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            fixture = self.fixture_directory(base)
            (fixture / "extra.json").write_bytes(b"{}")
            with mock.patch.object(c3_session.c2, "run_zero_write_preview") as c1:
                with self.assertRaises(c3_session.C3NamedSessionPreviewError):
                    c3_session.run_zero_write_preview(input_dir=fixture)
                c1.assert_not_called()

            fixture = base / "safe"
            fixture.mkdir()
            for name in c3_session.FIXTURE_FILE_NAMES:
                (fixture / name).write_bytes(b"harmless test placeholder")
            target = base / "target"
            target.write_bytes(b"harmless")
            os.unlink(fixture / "original.bin")
            os.symlink(target, fixture / "original.bin")
            with mock.patch.object(c3_session.c2, "run_zero_write_preview") as c1:
                with self.assertRaises(c3_session.C3NamedSessionPreviewError):
                    c3_session.run_zero_write_preview(input_dir=fixture)
                c1.assert_not_called()

    def test_confirmation_refuses_before_preview_or_socket_use(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            fixture = self.fixture_directory(Path(directory))
            with mock.patch.object(c3_session, "run_zero_write_preview") as preview:
                with contextlib.redirect_stderr(io.StringIO()):
                    self.assertEqual(
                        c3_session.main(
                            ["--input-dir", str(fixture), "--confirm-c3-local-transport-proof"]
                        ),
                        2,
                    )
                preview.assert_not_called()

    def test_runner_has_no_socket_session_or_lifecycle_import(self) -> None:
        source = Path(c3_session.__file__).read_text(encoding="utf-8")
        imports = set()
        attributes = set()
        for node in ast.walk(ast.parse(source)):
            if isinstance(node, ast.Import):
                imports.update(alias.name.split(".")[0] for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imports.add(node.module.split(".")[0])
            elif isinstance(node, ast.Attribute):
                attributes.add(node.attr)
        self.assertTrue({"socket", "subprocess", "urllib", "http", "requests"}.isdisjoint(imports))
        self.assertTrue({"bind", "listen", "accept", "connect", "send", "recv", "sendmsg", "recvmsg"}.isdisjoint(attributes))
        self.assertNotIn("pios_synthetic_source_ingress", source)


if __name__ == "__main__":
    unittest.main()
