"""Narrow local-only C3 Unix-socket transport foundation.

This module intentionally stops before a C3 listener protocol, a Corebox
client, fixed-fixture handoff, or lifecycle submission.  It provides only the
fail-closed primitives that a later, separately approved C3 runner may use:

* a macOS ``getpeereid(3)`` effective-UID check for an already-connected
  ``AF_UNIX`` stream socket;
* fresh private runtime-directory and socket creation/cleanup; and
* canonical challenge/request binding and exact-duplicate comparison.

It does not create TCP/UDP/loopback listeners, use a credential, retain a
nonce, open a network connection, or invoke the synthetic lifecycle.
"""
from __future__ import annotations

import ctypes
import os
import re
import secrets
import socket
import stat
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

from scripts import pios_canonical_source_primitives as primitives

PROTOCOL = "pios_solo_c3_local_transport_v1"
CHALLENGE_SCHEMA = "pios_solo_c3_local_challenge_v1"
REQUEST_SCHEMA = "pios_solo_c3_local_request_v1"
RECEIPT_RESPONSE_SCHEMA = "pios_solo_c3_local_receipt_response_v1"
MAX_FRAME_BYTES = 16 * 1024
FIXTURE_ID = "corebox_c2_harmless_text_v1"
PROOF_ID_RE = re.compile(r"c3-[a-z0-9]+(?:-[a-z0-9]+){2,63}")
UTC_TIMESTAMP_RE = re.compile(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z")
_FIXED_C2_FIXTURE_INTEGRITY_ITEMS = (
    ("envelope", "d1c0f4c1d41872f85e5c23331b593413615577524a0fa12ed81086b497370d5d", 3185),
    ("original", "557dcfaa13fcd79c59a61a0dc7d292aedf96ca4bf9aa41908b0ade40726be679", 42),
    ("zero_write_preview", "0a6cc21d9dd0a616558a2e47995fd9c6ad32ebe1e7d38946a8ebe96e6285b732", 776),
    ("fixture_manifest", "19e7cc9c57df09cbdea8711e5684257279578a18c39fcde8a92851a26a2245a7", 870),
)


class C3TransportError(ValueError):
    """Raised whenever a C3 local-transport primitive fails closed."""


@dataclass(frozen=True)
class PeerCredentials:
    """Effective credentials read from a connected local Unix-socket peer."""

    effective_uid: int
    effective_gid: int


def _require_unix_stream(sock: socket.socket) -> None:
    if not isinstance(sock, socket.socket):
        raise C3TransportError("peer credential lookup requires a socket")
    if sock.family != socket.AF_UNIX or (sock.type & 0xF) != socket.SOCK_STREAM:
        raise C3TransportError("C3 accepts only connected AF_UNIX stream sockets")


def getpeereid_credentials(sock: socket.socket) -> PeerCredentials:
    """Return effective peer UID/GID through the audited macOS getpeereid ABI.

    ``getpeereid(int, uid_t *, gid_t *)`` is a BSD/macOS system call.  The
    wrapper deliberately has no fallback: if the Darwin ABI is unavailable or
    fails, a later listener must refuse the peer before issuing a challenge.
    ``uid_t`` and ``gid_t`` are 32-bit unsigned integers on the supported
    macOS ABI.
    """
    _require_unix_stream(sock)
    if os.uname().sysname != "Darwin":
        raise C3TransportError("C3 getpeereid peer verification is macOS-only")
    try:
        libc = ctypes.CDLL("/usr/lib/libSystem.B.dylib", use_errno=True)
        getpeereid = libc.getpeereid
    except (AttributeError, OSError) as exc:
        raise C3TransportError("macOS getpeereid(3) is unavailable") from exc
    getpeereid.argtypes = [ctypes.c_int, ctypes.POINTER(ctypes.c_uint), ctypes.POINTER(ctypes.c_uint)]
    getpeereid.restype = ctypes.c_int
    peer_uid = ctypes.c_uint()
    peer_gid = ctypes.c_uint()
    if getpeereid(sock.fileno(), ctypes.byref(peer_uid), ctypes.byref(peer_gid)) != 0:
        error_number = ctypes.get_errno()
        raise C3TransportError("macOS getpeereid(3) peer lookup failed") from OSError(
            error_number, os.strerror(error_number)
        )
    return PeerCredentials(effective_uid=peer_uid.value, effective_gid=peer_gid.value)


def require_same_effective_uid(sock: socket.socket, *, expected_uid: int | None = None) -> PeerCredentials:
    """Require peer and listener effective UID equality without logging either UID."""
    peer = getpeereid_credentials(sock)
    listener_uid = os.geteuid() if expected_uid is None else expected_uid
    if not isinstance(listener_uid, int) or listener_uid < 0:
        raise C3TransportError("expected listener effective UID is invalid")
    if peer.effective_uid != listener_uid:
        raise C3TransportError("Unix-socket peer effective UID does not match listener")
    return peer


def fixed_c2_fixture_integrities() -> dict[str, dict[str, Any]]:
    """Return a fresh copy of the only fixture integrity set eligible for C3."""
    return {
        name: {"sha256": sha256, "byte_count": byte_count}
        for name, sha256, byte_count in _FIXED_C2_FIXTURE_INTEGRITY_ITEMS
    }


def _validate_private_directory(path: Path) -> Path:
    try:
        details = os.lstat(path)
    except FileNotFoundError as exc:
        raise C3TransportError("private C3 runtime directory is missing") from exc
    if stat.S_ISLNK(details.st_mode) or not stat.S_ISDIR(details.st_mode):
        raise C3TransportError("private C3 runtime path must be a real directory")
    if details.st_uid != os.geteuid() or stat.S_IMODE(details.st_mode) != 0o700:
        raise C3TransportError("private C3 runtime directory owner or mode is unsafe")
    return path


def create_private_runtime_directory(parent: Path) -> Path:
    """Create and verify one fresh, owner-only C3 runtime directory."""
    parent = Path(parent)
    if not parent.is_absolute():
        raise C3TransportError("C3 runtime parent must be an absolute local path")
    if not parent.is_dir() or parent.is_symlink():
        raise C3TransportError("C3 runtime parent must be an existing non-symlink directory")
    runtime = Path(tempfile.mkdtemp(prefix="pios-c3-", dir=parent))
    try:
        os.chmod(runtime, 0o700)
        return _validate_private_directory(runtime)
    except Exception:
        try:
            os.rmdir(runtime)
        except OSError:
            pass
        raise


def cleanup_private_runtime_directory(runtime: Path) -> None:
    """Remove only an empty verified private C3 runtime directory."""
    runtime = _validate_private_directory(Path(runtime))
    os.rmdir(runtime)
    if runtime.exists():
        raise C3TransportError("C3 runtime cleanup did not remove the private directory")


def _unlink_owned_socket(socket_path: Path) -> None:
    try:
        details = os.lstat(socket_path)
    except FileNotFoundError:
        return
    if stat.S_ISLNK(details.st_mode) or not stat.S_ISSOCK(details.st_mode):
        raise C3TransportError("C3 cleanup refuses a non-socket or symlink replacement")
    if details.st_uid != os.geteuid() or stat.S_IMODE(details.st_mode) != 0o600:
        raise C3TransportError("C3 cleanup refuses an unsafe socket owner or mode")
    os.unlink(socket_path)


def bind_private_unix_listener(runtime: Path) -> tuple[socket.socket, Path]:
    """Bind one private AF_UNIX listener beneath a verified fresh runtime path."""
    runtime = _validate_private_directory(Path(runtime))
    socket_path = runtime / "handoff.sock"
    if socket_path.exists() or socket_path.is_symlink():
        raise C3TransportError("C3 socket path already exists or is unsafe")
    prior_umask = os.umask(0o077)
    listener: socket.socket | None = None
    try:
        listener = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        listener.bind(str(socket_path))
        os.chmod(socket_path, 0o600)
        details = os.lstat(socket_path)
        if stat.S_ISLNK(details.st_mode) or not stat.S_ISSOCK(details.st_mode):
            raise C3TransportError("C3 listener did not create a Unix-socket filesystem node")
        if details.st_uid != os.geteuid() or stat.S_IMODE(details.st_mode) != 0o600:
            raise C3TransportError("C3 socket owner or mode is unsafe")
        listener.listen(1)
        return listener, socket_path
    except Exception:
        if listener is not None:
            listener.close()
        _unlink_owned_socket(socket_path)
        raise
    finally:
        os.umask(prior_umask)


def cleanup_private_unix_listener(listener: socket.socket, runtime: Path, socket_path: Path) -> None:
    """Close and remove only the verified private listener/socket/runtime trio."""
    runtime = _validate_private_directory(Path(runtime))
    socket_path = Path(socket_path)
    if socket_path.parent != runtime or socket_path.name != "handoff.sock":
        raise C3TransportError("C3 cleanup refuses an unexpected socket path")
    listener.close()
    _unlink_owned_socket(socket_path)
    os.rmdir(runtime)
    if socket_path.exists() or runtime.exists():
        raise C3TransportError("C3 listener cleanup did not remove all private runtime paths")


def _canonical_frame_value(value: Mapping[str, Any]) -> bytes:
    if not isinstance(value, Mapping):
        raise C3TransportError("C3 frames must contain one JSON object")
    encoded = primitives.canonical_json_bytes(value)
    if len(encoded) > MAX_FRAME_BYTES:
        raise C3TransportError("C3 canonical frame exceeds the 16 KiB limit")
    return encoded


def encode_canonical_frame(value: Mapping[str, Any]) -> bytes:
    """Encode one canonical JSON frame; transport I/O is intentionally absent."""
    encoded = _canonical_frame_value(value)
    return len(encoded).to_bytes(4, byteorder="big") + encoded


def validate_canonical_frame(frame: bytes) -> dict[str, Any]:
    """Validate an exact single length-prefixed canonical JSON frame."""
    if not isinstance(frame, bytes) or len(frame) < 4:
        raise C3TransportError("C3 frame is missing its length prefix")
    length = int.from_bytes(frame[:4], byteorder="big")
    body = frame[4:]
    if length != len(body) or length > MAX_FRAME_BYTES:
        raise C3TransportError("C3 frame length is invalid or exceeds the limit")
    try:
        import json

        value = json.loads(body.decode("utf-8"))
    except (UnicodeDecodeError, ValueError) as exc:
        raise C3TransportError("C3 frame is not UTF-8 JSON") from exc
    if not isinstance(value, dict) or _canonical_frame_value(value) != body:
        raise C3TransportError("C3 frame JSON is not canonical")
    return value


def _receive_exact(sock: socket.socket, length: int) -> bytes:
    if not isinstance(length, int) or length < 0:
        raise C3TransportError("C3 frame length is invalid")
    chunks: list[bytes] = []
    remaining = length
    while remaining:
        chunk = sock.recv(remaining)
        if not chunk:
            raise C3TransportError("C3 peer closed before one complete frame")
        chunks.append(chunk)
        remaining -= len(chunk)
    return b"".join(chunks)


def receive_canonical_frame(sock: socket.socket) -> dict[str, Any]:
    """Read one bounded frame with ordinary ``recv`` only; no ancillary data."""
    _require_unix_stream(sock)
    prefix = _receive_exact(sock, 4)
    length = int.from_bytes(prefix, byteorder="big")
    if length > MAX_FRAME_BYTES:
        raise C3TransportError("C3 frame length exceeds the 16 KiB limit")
    return validate_canonical_frame(prefix + _receive_exact(sock, length))


def send_canonical_frame(sock: socket.socket, value: Mapping[str, Any]) -> None:
    """Send one bounded frame with ordinary ``sendall`` only; no ancillary data."""
    _require_unix_stream(sock)
    sock.sendall(encode_canonical_frame(value))


def _proof_id(value: str) -> str:
    if not isinstance(value, str) or not PROOF_ID_RE.fullmatch(value):
        raise C3TransportError("C3 proof ID must be a bounded lowercase hyphenated token")
    return value


def _receipt_time(value: str) -> str:
    if not isinstance(value, str) or not UTC_TIMESTAMP_RE.fullmatch(value):
        raise C3TransportError("C3 receipt time must be UTC whole-second RFC3339")
    return value


def _fixture_integrities(value: Mapping[str, Any]) -> dict[str, dict[str, Any]]:
    required = {"envelope", "original", "zero_write_preview", "fixture_manifest"}
    if not isinstance(value, Mapping) or set(value) != required:
        raise C3TransportError("C3 requires exactly four fixed-fixture integrity records")
    normalized = {name: primitives.validate_integrity(value[name]) for name in sorted(required)}
    if normalized != fixed_c2_fixture_integrities():
        raise C3TransportError("C3 accepts only the approved immutable C2 fixture integrities")
    return normalized


def _nonce_bytes(nonce: bytes | None) -> bytes:
    nonce = secrets.token_bytes(32) if nonce is None else nonce
    if not isinstance(nonce, bytes) or len(nonce) != 32:
        raise C3TransportError("C3 challenge nonce must be exactly 32 ephemeral bytes")
    return nonce


def build_challenge(*, proof_id: str, fixture_manifest_sha256: str, nonce: bytes | None = None) -> dict[str, str]:
    """Build an in-memory, one-connection challenge without retaining it."""
    fixture_manifest_sha256 = primitives.validate_integrity(
        {"sha256": fixture_manifest_sha256, "byte_count": 0}
    )["sha256"]
    if fixture_manifest_sha256 != fixed_c2_fixture_integrities()["fixture_manifest"]["sha256"]:
        raise C3TransportError("C3 accepts only the approved immutable C2 fixture manifest")
    nonce = _nonce_bytes(nonce)
    return {
        "schema_version": CHALLENGE_SCHEMA,
        "protocol": PROTOCOL,
        "proof_id": _proof_id(proof_id),
        "challenge_nonce": nonce.hex(),
        "fixture_manifest_sha256": fixture_manifest_sha256,
    }


def _validated_challenge(challenge: Mapping[str, Any]) -> dict[str, str]:
    if not isinstance(challenge, Mapping) or set(challenge) != {
        "schema_version", "protocol", "proof_id", "challenge_nonce", "fixture_manifest_sha256"
    }:
        raise C3TransportError("C3 challenge has a non-canonical shape")
    if challenge.get("schema_version") != CHALLENGE_SCHEMA or challenge.get("protocol") != PROTOCOL:
        raise C3TransportError("C3 challenge schema or protocol is invalid")
    _proof_id(challenge.get("proof_id"))
    try:
        nonce = bytes.fromhex(challenge.get("challenge_nonce"))
    except (TypeError, ValueError) as exc:
        raise C3TransportError("C3 challenge nonce encoding is invalid") from exc
    _nonce_bytes(nonce)
    digest = primitives.validate_integrity(
        {"sha256": challenge.get("fixture_manifest_sha256"), "byte_count": 0}
    )["sha256"]
    if digest != fixed_c2_fixture_integrities()["fixture_manifest"]["sha256"]:
        raise C3TransportError("C3 challenge names an unapproved fixture manifest")
    return {
        "schema_version": CHALLENGE_SCHEMA,
        "protocol": PROTOCOL,
        "proof_id": challenge["proof_id"],
        "challenge_nonce": nonce.hex(),
        "fixture_manifest_sha256": digest,
    }


def derive_semantic_request_id(
    *, proof_id: str, fixture_integrities: Mapping[str, Any], receipt_recorded_at: str
) -> str:
    binding = {
        "schema_version": REQUEST_SCHEMA,
        "protocol": PROTOCOL,
        "proof_id": _proof_id(proof_id),
        "fixture_id": FIXTURE_ID,
        "fixture_integrities": _fixture_integrities(fixture_integrities),
        "receipt_recorded_at": _receipt_time(receipt_recorded_at),
    }
    return f"req_{primitives.sha256_bytes(primitives.canonical_json_bytes(binding))}"


def derive_connection_binding_hash(*, semantic_request_id: str, challenge: Mapping[str, Any]) -> str:
    if not isinstance(semantic_request_id, str) or not re.fullmatch(r"req_[0-9a-f]{64}", semantic_request_id):
        raise C3TransportError("C3 semantic request ID is invalid")
    safe_challenge = _validated_challenge(challenge)
    binding = {
        "schema_version": REQUEST_SCHEMA,
        "protocol": PROTOCOL,
        "semantic_request_id": semantic_request_id,
        "challenge_nonce": safe_challenge["challenge_nonce"],
    }
    return primitives.sha256_bytes(primitives.canonical_json_bytes(binding))


def build_fixed_fixture_request(
    *,
    challenge: Mapping[str, Any],
    fixture_integrities: Mapping[str, Any],
    receipt_recorded_at: str,
) -> dict[str, Any]:
    """Build the only C3 request shape; it contains integrity metadata, not data."""
    safe_challenge = _validated_challenge(challenge)
    integrities = _fixture_integrities(fixture_integrities)
    semantic_request_id = derive_semantic_request_id(
        proof_id=safe_challenge["proof_id"],
        fixture_integrities=integrities,
        receipt_recorded_at=receipt_recorded_at,
    )
    return {
        "schema_version": REQUEST_SCHEMA,
        "protocol": PROTOCOL,
        "operation": "submit_fixed_fixture",
        "proof_id": safe_challenge["proof_id"],
        "fixture_id": FIXTURE_ID,
        "fixture_manifest_sha256": safe_challenge["fixture_manifest_sha256"],
        "challenge_nonce": safe_challenge["challenge_nonce"],
        "fixture_integrities": integrities,
        "receipt_recorded_at": _receipt_time(receipt_recorded_at),
        "semantic_request_id": semantic_request_id,
        "connection_binding_hash": derive_connection_binding_hash(
            semantic_request_id=semantic_request_id, challenge=safe_challenge
        ),
    }


def validate_fixed_fixture_request(
    request: Mapping[str, Any],
    *,
    challenge: Mapping[str, Any],
    fixture_integrities: Mapping[str, Any],
    receipt_recorded_at: str,
) -> dict[str, Any]:
    """Require exact challenge and four-record fixture binding before lifecycle work."""
    safe_challenge = _validated_challenge(challenge)
    expected = build_fixed_fixture_request(
        challenge=safe_challenge,
        fixture_integrities=fixture_integrities,
        receipt_recorded_at=receipt_recorded_at,
    )
    if not isinstance(request, Mapping) or primitives.canonical_json_value(request) != expected:
        raise C3TransportError("C3 request does not exactly match the fixed-fixture binding")
    return expected


def require_exact_duplicate(first_request: Mapping[str, Any], duplicate_request: Mapping[str, Any]) -> dict[str, Any]:
    """Accept a duplicate only when its canonical request bytes are identical."""
    first = _canonical_frame_value(first_request)
    duplicate = _canonical_frame_value(duplicate_request)
    if duplicate != first:
        raise C3TransportError("C3 duplicate request is not an exact canonical repeat")
    return primitives.canonical_json_value(first_request)


def build_receipt_response(
    *, semantic_request_id: str, status: str, receipt: Mapping[str, Any]
) -> dict[str, Any]:
    """Build the only accepted/duplicate response shape for a future C3 session."""
    if status not in {"accepted", "duplicate"}:
        raise C3TransportError("C3 receipt response status must be accepted or duplicate")
    if not isinstance(receipt, Mapping):
        raise C3TransportError("C3 receipt response requires one receipt object")
    if not isinstance(semantic_request_id, str) or not re.fullmatch(r"req_[0-9a-f]{64}", semantic_request_id):
        raise C3TransportError("C3 semantic request ID is invalid")
    return {
        "schema_version": RECEIPT_RESPONSE_SCHEMA,
        "request_id": semantic_request_id,
        "status": status,
        "receipt": primitives.canonical_json_value(receipt),
    }


def validate_receipt_response(
    response: Mapping[str, Any], *, semantic_request_id: str, status: str
) -> dict[str, Any]:
    expected = build_receipt_response(
        semantic_request_id=semantic_request_id,
        status=status,
        receipt=response.get("receipt") if isinstance(response, Mapping) else {},
    )
    if not isinstance(response, Mapping) or primitives.canonical_json_value(response) != expected:
        raise C3TransportError("C3 receipt response is not bound to the request and status")
    return expected
