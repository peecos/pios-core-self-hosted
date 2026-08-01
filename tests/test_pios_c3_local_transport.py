import ast
import copy
import os
import socket
import stat
import tempfile
import unittest
from pathlib import Path

from scripts import pios_c3_local_transport as c3


FIXTURE_INTEGRITIES = c3.fixed_c2_fixture_integrities()


class C3LocalTransportFoundationTests(unittest.TestCase):
    def challenge(self, nonce: bytes = b"c" * 32):
        return c3.build_challenge(
            proof_id="c3-corebox-local-20260801-r1",
            fixture_manifest_sha256=FIXTURE_INTEGRITIES["fixture_manifest"]["sha256"],
            nonce=nonce,
        )

    def request(self, challenge=None, receipt_time="2026-08-01T00:00:03Z"):
        return c3.build_fixed_fixture_request(
            challenge=self.challenge() if challenge is None else challenge,
            fixture_integrities=FIXTURE_INTEGRITIES,
            receipt_recorded_at=receipt_time,
        )

    def test_macos_getpeereid_same_uid_is_required_on_local_socket_pair(self) -> None:
        left, right = socket.socketpair(socket.AF_UNIX, socket.SOCK_STREAM)
        try:
            peer = c3.require_same_effective_uid(left)
            self.assertEqual(peer.effective_uid, os.geteuid())
            self.assertGreaterEqual(peer.effective_gid, 0)
            with self.assertRaises(c3.C3TransportError):
                c3.require_same_effective_uid(left, expected_uid=os.geteuid() + 1)
        finally:
            left.close()
            right.close()

    def test_private_listener_has_owner_only_modes_and_cleanup(self) -> None:
        with tempfile.TemporaryDirectory() as parent:
            runtime = c3.create_private_runtime_directory(Path(parent))
            self.assertEqual(stat.S_IMODE(os.lstat(runtime).st_mode), 0o700)
            listener, socket_path = c3.bind_private_unix_listener(runtime)
            self.assertEqual(listener.family, socket.AF_UNIX)
            self.assertTrue(stat.S_ISSOCK(os.lstat(socket_path).st_mode))
            self.assertEqual(stat.S_IMODE(os.lstat(socket_path).st_mode), 0o600)
            c3.cleanup_private_unix_listener(listener, runtime, socket_path)
            self.assertFalse(runtime.exists())
            self.assertFalse(socket_path.exists())

    def test_runtime_safety_and_unexpected_cleanup_path_fail_closed(self) -> None:
        with tempfile.TemporaryDirectory() as parent:
            parent_path = Path(parent)
            runtime = c3.create_private_runtime_directory(parent_path)
            listener, socket_path = c3.bind_private_unix_listener(runtime)
            with self.assertRaises(c3.C3TransportError):
                c3.cleanup_private_unix_listener(listener, runtime, runtime / "other.sock")
            self.assertTrue(socket_path.exists())
            c3.cleanup_private_unix_listener(listener, runtime, socket_path)
            unsafe = parent_path / "unsafe"
            unsafe.mkdir(mode=0o755)
            os.chmod(unsafe, 0o755)
            with self.assertRaises(c3.C3TransportError):
                c3.bind_private_unix_listener(unsafe)

    def test_frames_are_canonical_bounded_and_reject_noncanonical_bytes(self) -> None:
        request = self.request()
        frame = c3.encode_canonical_frame(request)
        self.assertEqual(c3.validate_canonical_frame(frame), request)
        noncanonical = b'{"schema_version":"x","protocol":"pios_solo_c3_local_transport_v1"}'
        malformed = len(noncanonical).to_bytes(4, "big") + noncanonical
        with self.assertRaises(c3.C3TransportError):
            c3.validate_canonical_frame(malformed)
        oversized = {"x": "a" * c3.MAX_FRAME_BYTES}
        with self.assertRaises(c3.C3TransportError):
            c3.encode_canonical_frame(oversized)

    def test_challenge_request_binding_is_deterministic_and_per_connection(self) -> None:
        first_challenge = self.challenge(b"a" * 32)
        second_challenge = self.challenge(b"b" * 32)
        first = self.request(first_challenge)
        repeat = self.request(first_challenge)
        second = self.request(second_challenge)
        self.assertEqual(first, repeat)
        self.assertEqual(first["semantic_request_id"], second["semantic_request_id"])
        self.assertNotEqual(first["connection_binding_hash"], second["connection_binding_hash"])
        self.assertEqual(
            c3.validate_fixed_fixture_request(
                first,
                challenge=first_challenge,
                fixture_integrities=FIXTURE_INTEGRITIES,
                receipt_recorded_at="2026-08-01T00:00:03Z",
            ),
            first,
        )
        with self.assertRaises(c3.C3TransportError):
            c3.validate_fixed_fixture_request(
                first,
                challenge=second_challenge,
                fixture_integrities=FIXTURE_INTEGRITIES,
                receipt_recorded_at="2026-08-01T00:00:03Z",
            )

    def test_only_exact_duplicate_and_fixed_fixture_inputs_are_accepted(self) -> None:
        first = self.request()
        self.assertEqual(c3.require_exact_duplicate(first, copy.deepcopy(first)), first)
        changed = copy.deepcopy(first)
        changed["receipt_recorded_at"] = "2026-08-01T00:00:04Z"
        with self.assertRaises(c3.C3TransportError):
            c3.require_exact_duplicate(first, changed)
        altered = copy.deepcopy(FIXTURE_INTEGRITIES)
        altered["original"]["sha256"] = "0" * 64
        with self.assertRaises(c3.C3TransportError):
            c3.validate_fixed_fixture_request(
                first,
                challenge=self.challenge(),
                fixture_integrities=altered,
                receipt_recorded_at="2026-08-01T00:00:03Z",
            )

    def test_module_cannot_add_network_or_ancillary_transport(self) -> None:
        source = Path(c3.__file__).read_text(encoding="utf-8")
        tree = ast.parse(source)
        names = {node.id for node in ast.walk(tree) if isinstance(node, ast.Name)}
        attributes = {node.attr for node in ast.walk(tree) if isinstance(node, ast.Attribute)}
        self.assertNotIn("AF_INET", names)
        self.assertNotIn("AF_INET6", names)
        self.assertNotIn("sendmsg", attributes)
        self.assertNotIn("recvmsg", attributes)
        self.assertNotIn("create_connection", attributes)
        self.assertNotIn("connect", attributes)
        self.assertNotIn("pios_synthetic_source_ingress", source)
        self.assertNotIn("pios_generic_source_lifecycle", source)


if __name__ == "__main__":
    unittest.main()
