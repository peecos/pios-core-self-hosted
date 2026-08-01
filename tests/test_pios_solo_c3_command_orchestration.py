import contextlib
import io
import os
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from scripts import plan_pios_solo_c3_command_orchestration as orchestration


class C3CommandOrchestrationTests(unittest.TestCase):
    def make_tool(self, root: Path) -> Path:
        tool = root / "corebox-c3-tool"
        tool.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
        tool.chmod(0o700)
        return tool

    def preview_fixture(self) -> dict:
        return {"fixture": {"fixture_id": "corebox_c2_harmless_text_v1"}}

    def build_plan(self, root: Path, *, tool: Path | None = None):
        return orchestration.build_named_session_plan(
            input_dir=root / "fixture",
            proof_id="c3-corebox-local-20260801-r2",
            receipt_recorded_at="2026-08-01T00:00:04Z",
            runtime_parent=Path("/private/tmp"),
            evidence_dir=root / "evidence",
            corebox_tool=tool or self.make_tool(root),
            solo_revision="ef40daf",
            corebox_revision="1566817",
        )

    def server_result(self) -> dict:
        return {
            "status": "passed",
            "cleanup": "passed",
            "proof_id": "c3-corebox-local-20260801-r2",
            "semantic_request_id": "req_" + "a" * 64,
            "connection_binding_hash": "b" * 64,
            "receipt_id": "rcpt_" + "c" * 64,
            "accepted_status": "accepted",
            "duplicate_status": "duplicate",
        }

    def client_result_bytes(self, result: dict | None = None) -> bytes:
        result = result or self.server_result()
        value = {
            "proof_id": result["proof_id"],
            "semantic_request_id": result["semantic_request_id"],
            "connection_binding_hash": result["connection_binding_hash"],
            "receipt_id": result["receipt_id"],
            "accepted_status": result["accepted_status"],
            "duplicate_status": result["duplicate_status"],
        }
        return orchestration.primitives.canonical_json_bytes(value) + b"\n"

    def execute_side_effect(self, root: Path, result: dict):
        runtime = root / "pios-c3-test"
        runtime.mkdir(mode=0o700)

        def execute(**kwargs):
            kwargs["on_listener_ready"](runtime, runtime / "handoff.sock")
            return result

        return execute

    def child(self, *, returncode: int = 0):
        child = mock.Mock()
        child.returncode = returncode
        child.poll.return_value = returncode
        child.wait.return_value = returncode
        return child

    def popen_writer(self, child, *, stdout: bytes = b"", stderr: bytes = b""):
        def start(_command, **kwargs):
            kwargs["stdout"].write(stdout)
            kwargs["stdout"].flush()
            kwargs["stderr"].write(stderr)
            kwargs["stderr"].flush()
            return child

        return start

    def test_preview_binds_exact_revisions_and_never_starts_child(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            with mock.patch.object(orchestration.session, "run_zero_write_preview", return_value=self.preview_fixture()):
                plan = self.build_plan(root)
            output = orchestration.preview(plan)
            self.assertEqual(output["status"], "prepared_not_authorized")
            self.assertEqual(output["revisions"], {
                "solo_server_revision": "ef40daf",
                "corebox_client_revision": "1566817",
                "command_orchestration_revision": "must_be_named_in_a_future_execution_decision",
                "corebox_command_interface_revision": "must_be_named_in_a_future_execution_decision",
            })
            self.assertFalse(output["child_process_started"])
            self.assertEqual(output["network_or_cloud_calls"], 0)
            self.assertNotIn(str(root), str(output))

    def test_wrong_revision_or_unsafe_tool_refuses_before_fixture_preview(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            tool = self.make_tool(root)
            with mock.patch.object(orchestration.session, "run_zero_write_preview") as fixture_preview:
                with self.assertRaises(orchestration.C3CommandOrchestrationError):
                    orchestration.build_named_session_plan(
                        input_dir=root / "fixture", proof_id="c3-corebox-local-20260801-r2",
                        receipt_recorded_at="2026-08-01T00:00:04Z", runtime_parent=Path("/private/tmp"),
                        evidence_dir=root / "evidence", corebox_tool=tool,
                        solo_revision="deadbee", corebox_revision="1566817",
                    )
                fixture_preview.assert_not_called()

    def test_prior_proof_id_is_rejected_before_fixture_preview(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            tool = self.make_tool(root)
            with mock.patch.object(orchestration.session, "run_zero_write_preview") as fixture_preview:
                with self.assertRaises(orchestration.C3CommandOrchestrationError):
                    orchestration.build_named_session_plan(
                        input_dir=root / "fixture", proof_id=orchestration.session.REVIEW_PROOF_ID,
                        receipt_recorded_at="2026-08-01T00:00:04Z", runtime_parent=Path("/private/tmp"),
                        evidence_dir=root / "evidence", corebox_tool=tool,
                        solo_revision="ef40daf", corebox_revision="1566817",
                    )
                fixture_preview.assert_not_called()
            tool.chmod(0o600)
            with mock.patch.object(orchestration.session, "run_zero_write_preview") as fixture_preview:
                with self.assertRaises(orchestration.C3CommandOrchestrationError):
                    self.build_plan(root, tool=tool)
                fixture_preview.assert_not_called()

    def test_execution_is_hard_disabled_before_subprocess_or_socket_path(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            with mock.patch.object(orchestration.session, "run_zero_write_preview", return_value=self.preview_fixture()):
                plan = self.build_plan(root)
            with mock.patch.object(orchestration.subprocess, "Popen") as process:
                with self.assertRaises(orchestration.C3CommandOrchestrationNotAuthorized):
                    orchestration.execute_named_session(plan, execution_authorized=True)
                process.assert_not_called()

    def test_cli_confirmation_refuses_without_starting_process(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            tool = self.make_tool(root)
            args = [
                "--input-dir", str(root / "fixture"), "--proof-id", "c3-corebox-local-20260801-r2",
                "--receipt-recorded-at", "2026-08-01T00:00:04Z", "--runtime-parent", "/private/tmp",
                "--evidence-dir", str(root / "evidence"), "--corebox-tool", str(tool),
                "--solo-revision", "ef40daf", "--corebox-revision", "1566817",
                "--confirm-c3-local-transport-orchestration",
            ]
            with (
                mock.patch.object(orchestration.session, "run_zero_write_preview", return_value=self.preview_fixture()),
                mock.patch.object(orchestration.subprocess, "Popen") as process,
                contextlib.redirect_stderr(io.StringIO()),
            ):
                self.assertEqual(orchestration.main(args), 2)
                process.assert_not_called()

    def test_pass_evidence_is_retained_only_after_child_receipt_matches(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            with mock.patch.object(orchestration.session, "run_zero_write_preview", return_value=self.preview_fixture()):
                plan = self.build_plan(root)
            server_result = self.server_result()
            child = self.child()
            with (
                mock.patch.object(orchestration, "ORCHESTRATION_EXECUTION_ENABLED", True),
                mock.patch.object(orchestration.subprocess, "Popen", side_effect=self.popen_writer(child, stdout=self.client_result_bytes(server_result))),
                mock.patch.object(orchestration.session, "execute_one_shot_session", side_effect=self.execute_side_effect(root, server_result)) as execute,
                mock.patch.object(orchestration.session, "retain_session_evidence") as retain,
            ):
                self.assertEqual(orchestration.execute_named_session(plan, execution_authorized=True), server_result)
                execute.assert_called_once()
                self.assertFalse(execute.call_args.kwargs["retain_evidence"])
                retain.assert_called_once_with(result=server_result, evidence_dir=plan.evidence_dir)

    def test_child_receipt_mismatch_never_retains_pass_evidence(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            with mock.patch.object(orchestration.session, "run_zero_write_preview", return_value=self.preview_fixture()):
                plan = self.build_plan(root)
            server_result = self.server_result()
            changed = dict(server_result)
            changed["receipt_id"] = "rcpt_" + "d" * 64
            child = self.child()
            with (
                mock.patch.object(orchestration, "ORCHESTRATION_EXECUTION_ENABLED", True),
                mock.patch.object(orchestration.subprocess, "Popen", side_effect=self.popen_writer(child, stdout=self.client_result_bytes(changed))),
                mock.patch.object(orchestration.session, "execute_one_shot_session", side_effect=self.execute_side_effect(root, server_result)),
                mock.patch.object(orchestration.session, "retain_session_evidence") as retain,
            ):
                with self.assertRaises(orchestration.C3CommandOrchestrationError):
                    orchestration.execute_named_session(plan, execution_authorized=True)
                retain.assert_not_called()

    def test_incomplete_or_malformed_child_json_never_retains_evidence(self) -> None:
        for output in [b'{"receipt_id":"rcpt_' + b"c" * 64 + b'"}\n', b"not-json\n", b"{}\n\n"]:
            with self.subTest(output=output), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                with mock.patch.object(orchestration.session, "run_zero_write_preview", return_value=self.preview_fixture()):
                    plan = self.build_plan(root)
                child = self.child()
                result = self.server_result()
                with (
                    mock.patch.object(orchestration, "ORCHESTRATION_EXECUTION_ENABLED", True),
                    mock.patch.object(orchestration.subprocess, "Popen", side_effect=self.popen_writer(child, stdout=output)),
                    mock.patch.object(orchestration.session, "execute_one_shot_session", side_effect=self.execute_side_effect(root, result)),
                    mock.patch.object(orchestration.session, "retain_session_evidence") as retain,
                ):
                    with self.assertRaises(orchestration.C3CommandOrchestrationError):
                        orchestration.execute_named_session(plan, execution_authorized=True)
                    retain.assert_not_called()

    def test_nonzero_child_exit_never_retains_evidence(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            with mock.patch.object(orchestration.session, "run_zero_write_preview", return_value=self.preview_fixture()):
                plan = self.build_plan(root)
            child = self.child(returncode=2)
            with (
                mock.patch.object(orchestration, "ORCHESTRATION_EXECUTION_ENABLED", True),
                mock.patch.object(orchestration.subprocess, "Popen", side_effect=self.popen_writer(child)),
                mock.patch.object(orchestration.session, "execute_one_shot_session", side_effect=self.execute_side_effect(root, self.server_result())),
                mock.patch.object(orchestration.session, "retain_session_evidence") as retain,
            ):
                with self.assertRaises(orchestration.C3CommandOrchestrationError):
                    orchestration.execute_named_session(plan, execution_authorized=True)
                retain.assert_not_called()

    def test_successful_child_with_stderr_never_retains_evidence(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            with mock.patch.object(orchestration.session, "run_zero_write_preview", return_value=self.preview_fixture()):
                plan = self.build_plan(root)
            child = self.child()
            result = self.server_result()
            with (
                mock.patch.object(orchestration, "ORCHESTRATION_EXECUTION_ENABLED", True),
                mock.patch.object(orchestration.subprocess, "Popen", side_effect=self.popen_writer(
                    child, stdout=self.client_result_bytes(result), stderr=b"unexpected\n"
                )),
                mock.patch.object(orchestration.session, "execute_one_shot_session", side_effect=self.execute_side_effect(root, result)),
                mock.patch.object(orchestration.session, "retain_session_evidence") as retain,
            ):
                with self.assertRaises(orchestration.C3CommandOrchestrationError):
                    orchestration.execute_named_session(plan, execution_authorized=True)
                retain.assert_not_called()

    def test_child_timeout_terminates_then_kills_and_never_retains_evidence(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            with mock.patch.object(orchestration.session, "run_zero_write_preview", return_value=self.preview_fixture()):
                plan = self.build_plan(root)
            child = mock.Mock()
            child.returncode = None
            child.poll.side_effect = [None, 0]
            child.wait.side_effect = [subprocess.TimeoutExpired("child", 45), subprocess.TimeoutExpired("child", 5), 0]
            with (
                mock.patch.object(orchestration, "ORCHESTRATION_EXECUTION_ENABLED", True),
                mock.patch.object(orchestration.subprocess, "Popen", side_effect=self.popen_writer(child)),
                mock.patch.object(orchestration.session, "execute_one_shot_session", side_effect=self.execute_side_effect(root, self.server_result())),
                mock.patch.object(orchestration.session, "retain_session_evidence") as retain,
            ):
                with self.assertRaises(orchestration.C3CommandOrchestrationError):
                    orchestration.execute_named_session(plan, execution_authorized=True)
                child.terminate.assert_called_once()
                child.kill.assert_called_once()
                retain.assert_not_called()

    def test_missing_child_callback_never_retains_evidence(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            with mock.patch.object(orchestration.session, "run_zero_write_preview", return_value=self.preview_fixture()):
                plan = self.build_plan(root)
            with (
                mock.patch.object(orchestration, "ORCHESTRATION_EXECUTION_ENABLED", True),
                mock.patch.object(orchestration.session, "execute_one_shot_session", return_value=self.server_result()),
                mock.patch.object(orchestration.session, "retain_session_evidence") as retain,
            ):
                with self.assertRaises(orchestration.C3CommandOrchestrationError):
                    orchestration.execute_named_session(plan, execution_authorized=True)
                retain.assert_not_called()

    def test_executable_replacement_is_rejected_before_popen(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            tool = self.make_tool(root)
            with mock.patch.object(orchestration.session, "run_zero_write_preview", return_value=self.preview_fixture()):
                plan = self.build_plan(root, tool=tool)
            tool.unlink()
            tool.write_text("#!/bin/sh\nexit 1\n", encoding="utf-8")
            tool.chmod(0o700)
            with (
                mock.patch.object(orchestration, "ORCHESTRATION_EXECUTION_ENABLED", True),
                mock.patch.object(orchestration.subprocess, "Popen") as process,
                mock.patch.object(orchestration.session, "execute_one_shot_session", side_effect=self.execute_side_effect(root, self.server_result())),
                mock.patch.object(orchestration.session, "retain_session_evidence") as retain,
            ):
                with self.assertRaises(orchestration.C3CommandOrchestrationError):
                    orchestration.execute_named_session(plan, execution_authorized=True)
                process.assert_not_called()
                retain.assert_not_called()

    def test_popen_failure_removes_private_executable_snapshot(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            with mock.patch.object(orchestration.session, "run_zero_write_preview", return_value=self.preview_fixture()):
                plan = self.build_plan(root)
            runtime = root / "pios-c3-test"
            runtime.mkdir(mode=0o700)

            def execute(**kwargs):
                kwargs["on_listener_ready"](runtime, runtime / "handoff.sock")
                return self.server_result()

            with (
                mock.patch.object(orchestration, "ORCHESTRATION_EXECUTION_ENABLED", True),
                mock.patch.object(orchestration.subprocess, "Popen", side_effect=OSError("launch failed")),
                mock.patch.object(orchestration.session, "execute_one_shot_session", side_effect=execute),
            ):
                with self.assertRaises(OSError):
                    orchestration.execute_named_session(plan, execution_authorized=True)
            self.assertFalse((runtime / "corebox-c3-client").exists())


if __name__ == "__main__":
    unittest.main()
