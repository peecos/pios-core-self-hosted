import contextlib
import io
import os
import stat
import tempfile
import unittest
import json
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
            server_result = {"status": "passed", "cleanup": "passed", "receipt_id": "rcpt_" + "a" * 64}
            child = mock.Mock()
            child.communicate.return_value = (json.dumps({"receipt_id": server_result["receipt_id"]}), "")
            child.returncode = 0
            child.poll.return_value = 0
            def execute_with_listener(**kwargs):
                kwargs["on_listener_ready"](Path("/private/tmp/pios-c3-test"), Path("/private/tmp/pios-c3-test/handoff.sock"))
                return server_result
            with (
                mock.patch.object(orchestration, "ORCHESTRATION_EXECUTION_ENABLED", True),
                mock.patch.object(orchestration.subprocess, "Popen", return_value=child),
                mock.patch.object(orchestration.session, "execute_one_shot_session", side_effect=execute_with_listener) as execute,
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
            server_result = {"status": "passed", "cleanup": "passed", "receipt_id": "rcpt_" + "a" * 64}
            child = mock.Mock()
            child.communicate.return_value = (json.dumps({"receipt_id": "rcpt_" + "b" * 64}), "")
            child.returncode = 0
            child.poll.return_value = 0
            def execute_with_listener(**kwargs):
                kwargs["on_listener_ready"](Path("/private/tmp/pios-c3-test"), Path("/private/tmp/pios-c3-test/handoff.sock"))
                return server_result
            with (
                mock.patch.object(orchestration, "ORCHESTRATION_EXECUTION_ENABLED", True),
                mock.patch.object(orchestration.subprocess, "Popen", return_value=child),
                mock.patch.object(orchestration.session, "execute_one_shot_session", side_effect=execute_with_listener),
                mock.patch.object(orchestration.session, "retain_session_evidence") as retain,
            ):
                with self.assertRaises(orchestration.C3CommandOrchestrationError):
                    orchestration.execute_named_session(plan, execution_authorized=True)
                retain.assert_not_called()


if __name__ == "__main__":
    unittest.main()
