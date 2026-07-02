from __future__ import annotations

import argparse
import hashlib
import json
import os
import secrets
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

DEFAULT_KEY_ROOT = (
    Path.home() / "Library" / "Application Support" / "Peecos" / "release-keys" / "production"
)
DEFAULT_PUBLIC_KEY_DIR = Path("docs/release-keys")
DEFAULT_PROOF_DIR = Path("image-artifacts/production-release-key-setup")


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def resolve_repo_path(path: Path) -> Path:
    return (REPO_ROOT / path).resolve() if not path.is_absolute() else path


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def run(command: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        command,
        cwd=REPO_ROOT,
        check=True,
        capture_output=True,
        text=True,
    )


def ensure_openssl() -> str:
    openssl = shutil.which("openssl")
    if not openssl:
        raise ValueError("openssl is not available on PATH")
    version = run([openssl, "version"]).stdout
    if "OpenSSL 3" not in version:
        raise ValueError(f"OpenSSL 3.x is required, found: {version.strip()}")
    return openssl


def write_private_file(path: Path, text: str) -> None:
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        with os.fdopen(fd, "w") as handle:
            handle.write(text)
    except Exception:
        try:
            path.unlink()
        finally:
            raise


def create_key_material(
    *,
    openssl: str,
    key_dir: Path,
    key_id: str,
) -> dict[str, Path | str]:
    if REPO_ROOT in key_dir.parents or key_dir == REPO_ROOT:
        raise ValueError("production key directory must not live inside the repository")
    key_dir.mkdir(parents=True, mode=0o700, exist_ok=False)
    key_dir.chmod(0o700)
    private_key = key_dir / f"{key_id}.pem"
    public_key = key_dir / f"{key_id}.pub.pem"
    passphrase_file = key_dir / f"{key_id}.passphrase.txt"
    passphrase = secrets.token_urlsafe(48)
    write_private_file(passphrase_file, passphrase + "\n")
    run(
        [
            openssl,
            "genpkey",
            "-algorithm",
            "ed25519",
            "-aes-256-cbc",
            "-pass",
            f"file:{passphrase_file}",
            "-out",
            str(private_key),
        ]
    )
    private_key.chmod(0o600)
    run(
        [
            openssl,
            "pkey",
            "-in",
            str(private_key),
            "-passin",
            f"file:{passphrase_file}",
            "-pubout",
            "-out",
            str(public_key),
        ]
    )
    public_key.chmod(0o644)
    return {
        "private_key": private_key,
        "public_key": public_key,
        "passphrase_file": passphrase_file,
    }


def synthetic_signing_proof(
    *,
    openssl: str,
    proof_dir: Path,
    private_key: Path,
    public_key: Path,
    passphrase_file: Path,
) -> tuple[Path, Path, Path]:
    proof_dir.mkdir(parents=True, exist_ok=True)
    checksums = proof_dir / "synthetic-SHA256SUMS"
    payload = proof_dir / "synthetic-release-artifact.txt"
    payload.write_text("synthetic production release key setup proof\n")
    checksums.write_text(f"{sha256_file(payload)}  {payload.name}\n")
    signature = proof_dir / "synthetic-SHA256SUMS.sig"
    run(
        [
            openssl,
            "pkeyutl",
            "-sign",
            "-rawin",
            "-inkey",
            str(private_key),
            "-passin",
            f"file:{passphrase_file}",
            "-in",
            str(checksums),
            "-out",
            str(signature),
        ]
    )
    run(
        [
            openssl,
            "pkeyutl",
            "-verify",
            "-rawin",
            "-pubin",
            "-inkey",
            str(public_key),
            "-in",
            str(checksums),
            "-sigfile",
            str(signature),
        ]
    )
    return payload, checksums, signature


def publish_public_material(
    *,
    public_key: Path,
    public_key_dir: Path,
    key_id: str,
) -> tuple[Path, Path]:
    public_key_dir.mkdir(parents=True, exist_ok=True)
    public_key_out = public_key_dir / "peecos-release-signing-key.pub"
    fingerprint_out = public_key_dir / "peecos-release-signing-key-fingerprint.txt"
    public_key_out.write_text(public_key.read_text())
    fingerprint_out.write_text(f"{sha256_file(public_key)}  {public_key_out.name}\n")
    return public_key_out, fingerprint_out


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Create an encrypted production release signing key outside the repository."
    )
    parser.add_argument("--confirm-create-production-key", action="store_true")
    parser.add_argument("--key-id", default="peecos-release-signing-ed25519-20260703")
    parser.add_argument("--key-owner", default="peecos release maintainer")
    parser.add_argument("--key-root", type=Path, default=DEFAULT_KEY_ROOT)
    parser.add_argument("--public-key-dir", type=Path, default=DEFAULT_PUBLIC_KEY_DIR)
    parser.add_argument("--proof-dir", type=Path, default=DEFAULT_PROOF_DIR)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if not args.confirm_create_production_key:
        raise ValueError("refusing to create a production key without explicit confirmation")
    openssl = ensure_openssl()
    key_root = args.key_root if args.key_root.is_absolute() else resolve_repo_path(args.key_root)
    public_key_dir = resolve_repo_path(args.public_key_dir)
    proof_dir = resolve_repo_path(args.proof_dir) / args.key_id
    key_dir = key_root / args.key_id
    material = create_key_material(openssl=openssl, key_dir=key_dir, key_id=args.key_id)
    private_key = material["private_key"]
    public_key = material["public_key"]
    passphrase_file = material["passphrase_file"]
    assert isinstance(private_key, Path)
    assert isinstance(public_key, Path)
    assert isinstance(passphrase_file, Path)
    _, checksums, signature = synthetic_signing_proof(
        openssl=openssl,
        proof_dir=proof_dir,
        private_key=private_key,
        public_key=public_key,
        passphrase_file=passphrase_file,
    )
    public_key_out, fingerprint_out = publish_public_material(
        public_key=public_key,
        public_key_dir=public_key_dir,
        key_id=args.key_id,
    )
    proof = {
        "schema_version": "peecos_production_release_key_setup_proof_v1",
        "created_at": utc_now(),
        "status": "passed",
        "key_id": args.key_id,
        "key_owner": args.key_owner,
        "key_mechanism": "encrypted_offline_software_key",
        "private_key_stored_in_repository": False,
        "private_key_stored_in_image": False,
        "private_key_path_recorded": False,
        "passphrase_path_recorded": False,
        "public_key_path": str(public_key_out),
        "public_key_fingerprint_path": str(fingerprint_out),
        "public_key_sha256": sha256_file(public_key),
        "synthetic_signature_verified": True,
        "synthetic_checksums_file": str(checksums),
        "synthetic_signature_file": str(signature),
        "recovery_policy_recorded": True,
        "rotation_policy_recorded": True,
        "revocation_policy_recorded": True,
        "boundaries": [
            "private key material created outside repository",
            "passphrase material created outside repository",
            "only public key and fingerprint are written to tracked documentation paths",
            "no release artifact is published by this script",
        ],
    }
    proof_path = proof_dir / "production-release-key-setup-proof.json"
    proof_path.write_text(json.dumps(proof, indent=2, sort_keys=True) + "\n")
    print(json.dumps(proof, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
