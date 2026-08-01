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
            base = Path(directory)
            fixture = self.fixture_directory(base)
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
            self.assertEqual(preview["revisions"], {
                "solo_foundation_commit": "45c5bac",
                "corebox_preview_contract_commit": "1db18d5",
                "corebox_execution_commit": "1566817",
            })
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
        self.assertTrue({"sendmsg", "recvmsg", "connect"}.isdisjoint(attributes))
        self.assertNotIn("AF_INET", source)
        self.assertNotIn("AF_INET6", source)
        self.assertIn("refuse_named_session_execution()", source)

    def test_execution_path_orders_same_euid_then_one_request_and_duplicate_with_mocks(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            fixture = self.fixture_directory(base)
            runtime = base / "runtime"
            runtime.mkdir()
            challenge = transport.build_challenge(
                proof_id=c3_session.REVIEW_PROOF_ID,
                fixture_manifest_sha256=transport.fixed_c2_fixture_integrities()["fixture_manifest"]["sha256"],
                nonce=b"a" * 32,
            )
            request = transport.build_fixed_fixture_request(
                challenge=challenge,
                fixture_integrities=transport.fixed_c2_fixture_integrities(),
                receipt_recorded_at=c3_session.REVIEW_RECEIPT_RECORDED_AT,
            )
            events: list[str] = []
            listener = FakeListener(events)
            connection = listener.connection
            accepted = {"receipt_id": "rcpt_" + "a" * 64}
            with (
                mock.patch.object(c3_session, "_fixture_preview", return_value=self.c1_preview()),
                mock.patch.object(c3_session, "_load_validated_lifecycle_input", return_value=({}, b"original")),
                mock.patch.object(c3_session.transport, "create_private_runtime_directory", return_value=runtime),
                mock.patch.object(c3_session.transport, "bind_private_unix_listener", return_value=(listener, runtime / "handoff.sock")),
                mock.patch.object(c3_session.transport, "require_same_effective_uid", side_effect=lambda _connection: events.append("same_euid")),
                mock.patch.object(c3_session.transport, "build_challenge", return_value=challenge),
                mock.patch.object(c3_session.transport, "send_canonical_frame", side_effect=lambda _connection, value: connection.sent.append(value)),
                mock.patch.object(c3_session.transport, "receive_canonical_frame", side_effect=[request, request]),
                mock.patch.object(c3_session, "_start_one_fixture_lifecycle", return_value=(object(), accepted)) as start,
                mock.patch.object(c3_session, "_finish_one_fixture_lifecycle", return_value=(accepted, {"cursor": 1})) as finish,
                mock.patch.object(c3_session.transport, "cleanup_private_unix_listener", side_effect=lambda *_args: events.append("cleanup")),
            ):
                result = c3_session.execute_one_shot_session(
                    input_dir=fixture,
                    proof_id=c3_session.REVIEW_PROOF_ID,
                    receipt_recorded_at=c3_session.REVIEW_RECEIPT_RECORDED_AT,
                    runtime_parent=Path("/private/tmp"),
                    evidence_dir=base / "evidence",
                    solo_revision="ef40daf",
                    corebox_revision="1566817",
                    execution_authorized=True,
                )
            self.assertEqual(events[:2], ["accept", "same_euid"])
            self.assertEqual(events[-1], "cleanup")
            self.assertTrue(connection.closed)
            self.assertEqual(connection.sent[0]["schema_version"], transport.CHALLENGE_SCHEMA)
            self.assertEqual([item["status"] for item in connection.sent[1:]], ["accepted", "duplicate"])
            self.assertEqual(connection.sent[1]["receipt"], accepted)
            self.assertEqual(result["receipt_id"], accepted["receipt_id"])
            start.assert_called_once()
            finish.assert_called_once()

    def test_execution_path_refuses_before_fixture_or_runtime_when_not_authorized(self) -> None:
        with mock.patch.object(c3_session, "_validate_fixed_fixture_path_safety") as fixture_check:
            with self.assertRaises(c3_session.C3NamedSessionExecutionNotAuthorized):
                c3_session.execute_one_shot_session(
                    input_dir=Path("/not-used"),
                    proof_id=c3_session.REVIEW_PROOF_ID,
                    receipt_recorded_at=c3_session.REVIEW_RECEIPT_RECORDED_AT,
                    runtime_parent=Path("/private/tmp"),
                    evidence_dir=Path("/private/tmp/not-used-evidence"),
                    solo_revision="195dffc",
                    corebox_revision="1566817",
                    execution_authorized=False,
                )
            fixture_check.assert_not_called()

    def test_execution_path_refuses_unreviewed_corebox_revision_before_fixture_or_runtime(self) -> None:
        with mock.patch.object(c3_session, "_validate_fixed_fixture_path_safety") as fixture_check:
            with self.assertRaises(c3_session.C3NamedSessionProtocolError):
                c3_session.execute_one_shot_session(
                    input_dir=Path("/not-used"),
                    proof_id=c3_session.REVIEW_PROOF_ID,
                    receipt_recorded_at=c3_session.REVIEW_RECEIPT_RECORDED_AT,
                    runtime_parent=Path("/private/tmp"),
                    evidence_dir=Path("/private/tmp/not-used-evidence"),
                    solo_revision="195dffc",
                    corebox_revision="deadbee",
                    execution_authorized=True,
                )
            fixture_check.assert_not_called()

    def test_execution_path_refuses_unreviewed_solo_revision_before_fixture_or_runtime(self) -> None:
        with mock.patch.object(c3_session, "_validate_fixed_fixture_path_safety") as fixture_check:
            with self.assertRaises(c3_session.C3NamedSessionProtocolError):
                c3_session.execute_one_shot_session(
                    input_dir=Path("/not-used"),
                    proof_id=c3_session.REVIEW_PROOF_ID,
                    receipt_recorded_at=c3_session.REVIEW_RECEIPT_RECORDED_AT,
                    runtime_parent=Path("/private/tmp"),
                    evidence_dir=Path("/private/tmp/not-used-evidence"),
                    solo_revision="195dffc",
                    corebox_revision="1566817",
                    execution_authorized=True,
                )
            fixture_check.assert_not_called()

    def test_execution_path_rejects_invalid_named_input_before_fixture_or_runtime(self) -> None:
        with mock.patch.object(c3_session, "_validate_fixed_fixture_path_safety") as fixture_check:
            with self.assertRaises(c3_session.C3NamedSessionProtocolError):
                c3_session.execute_one_shot_session(
                    input_dir=Path("/not-used"),
                    proof_id="invalid proof id",
                    receipt_recorded_at=c3_session.REVIEW_RECEIPT_RECORDED_AT,
                    runtime_parent=Path("/private/tmp"),
                    evidence_dir=Path("/private/tmp/not-used-evidence"),
                    solo_revision="ef40daf",
                    corebox_revision="1566817",
                    execution_authorized=True,
                )
            fixture_check.assert_not_called()

    def test_named_confirmation_requires_all_explicit_bindings_and_reviewed_client_revision(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            fixture = self.fixture_directory(Path(directory))
            with contextlib.redirect_stderr(io.StringIO()):
                self.assertEqual(
                    c3_session.main(["--input-dir", str(fixture), "--confirm-c3-local-transport-proof"]),
                    2,
                )
                self.assertEqual(
                    c3_session.main([
                        "--input-dir", str(fixture),
                        "--confirm-c3-local-transport-proof",
                        "--proof-id", c3_session.REVIEW_PROOF_ID,
                        "--receipt-recorded-at", c3_session.REVIEW_RECEIPT_RECORDED_AT,
                        "--runtime-parent", "/private/tmp",
                        "--evidence-dir", str(Path(directory) / "evidence"),
                        "--solo-revision", "ef40daf",
                        "--corebox-revision", "deadbee",
                    ]),
                    2,
                )


class FakeConnection:
    def __init__(self) -> None:
        self.sent: list[dict] = []
        self.closed = False

    def close(self) -> None:
        self.closed = True

    def settimeout(self, _timeout: int) -> None:
        return None


class FakeListener:
    def __init__(self, events: list[str]) -> None:
        self.events = events
        self.connection = FakeConnection()

    def settimeout(self, _timeout: int) -> None:
        return None

    def accept(self):
        self.events.append("accept")
        return self.connection, object()


if __name__ == "__main__":
    unittest.main()
