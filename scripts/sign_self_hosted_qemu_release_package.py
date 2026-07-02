from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

DEFAULT_VALIDATION_RESULT = Path(
    "image-artifacts/qemu-release-package/pios-core-self-hosted-qemu-arm64-20260702-validation-result.json"
)
DEFAULT_OUTPUT_DIR = Path("image-artifacts/qemu-release-signing")
DEFAULT_KEY_DIR = Path("image-artifacts/qemu-release-signing/local-dev-release-key")


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def resolve_repo_path(path: Path) -> Path:
    return (REPO_ROOT / path).resolve() if not path.is_absolute() else path


def run(command: list[str], *, capture: bool = True) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        command,
        cwd=REPO_ROOT,
        check=True,
        capture_output=capture,
        text=True,
    )


def load_json(path: Path) -> dict[str, Any]:
    try:
        return json.loads(path.read_text())
    except json.JSONDecodeError as exc:
        raise ValueError(f"invalid JSON file: {path}") from exc


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def ensure_openssl() -> str:
    openssl = shutil.which("openssl")
    if not openssl:
        raise ValueError("openssl is not available on PATH")
    return openssl


def ensure_dev_signing_key(*, key_dir: Path, openssl: str) -> tuple[Path, Path]:
    key_dir.mkdir(parents=True, exist_ok=True)
    private_key = key_dir / "local-dev-release-signing-ed25519.pem"
    public_key = key_dir / "local-dev-release-signing-ed25519.pub.pem"
    if not private_key.exists():
        run([openssl, "genpkey", "-algorithm", "ed25519", "-out", str(private_key)])
        private_key.chmod(0o600)
    if not public_key.exists():
        run([openssl, "pkey", "-in", str(private_key), "-pubout", "-out", str(public_key)])
    if private_key.stat().st_mode & 0o077:
        private_key.chmod(0o600)
    return private_key, public_key


def public_key_fingerprint(public_key: Path) -> str:
    return sha256_file(public_key)


def write_checksums(*, files: list[Path], output: Path) -> None:
    lines = []
    for path in sorted(files, key=lambda item: item.name):
        if not path.is_file():
            raise ValueError(f"file to checksum is missing: {path}")
        lines.append(f"{sha256_file(path)}  {path.name}")
    output.write_text("\n".join(lines) + "\n")


def sign_file(
    *,
    openssl: str,
    private_key: Path,
    file_to_sign: Path,
    signature: Path,
    passphrase_file: Path | None = None,
) -> None:
    if signature.exists():
        signature.unlink()
    command = [
        openssl,
        "pkeyutl",
        "-sign",
        "-rawin",
        "-inkey",
        str(private_key),
    ]
    if passphrase_file is not None:
        command.extend(["-passin", f"file:{passphrase_file}"])
    command.extend(["-in", str(file_to_sign), "-out", str(signature)])
    run(command)


def verify_signature(*, openssl: str, public_key: Path, file_to_verify: Path, signature: Path) -> None:
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
            str(file_to_verify),
            "-sigfile",
            str(signature),
        ]
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Create and verify local development signatures for the self-hosted QEMU release package."
    )
    parser.add_argument("--validation-result", type=Path, default=DEFAULT_VALIDATION_RESULT)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--key-dir", type=Path, default=DEFAULT_KEY_DIR)
    parser.add_argument("--private-key", type=Path)
    parser.add_argument("--public-key", type=Path)
    parser.add_argument("--passphrase-file", type=Path)
    parser.add_argument(
        "--key-scope",
        choices=["local_development_release_signing_proof", "peecos_production_release_key"],
        default="local_development_release_signing_proof",
    )
    parser.add_argument(
        "--extra-artifact",
        action="append",
        type=Path,
        default=[],
        help="Additional public release artifact to include in SHA256SUMS.",
    )
    parser.add_argument("--release-id", default="pios-core-self-hosted-qemu-arm64-20260702")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    openssl = ensure_openssl()
    validation_result_path = resolve_repo_path(args.validation_result)
    output_dir = resolve_repo_path(args.output_dir)
    key_dir = resolve_repo_path(args.key_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    validation_result = load_json(validation_result_path)
    if validation_result.get("status") != "passed":
        raise ValueError("validation result must have status=passed")
    package = validation_result["package"]
    package_archive = Path(package["package_archive"])
    if not package_archive.is_absolute():
        package_archive = resolve_repo_path(package_archive)
    package_manifest = output_dir.parent / "qemu-release-package" / f"{package['package_id']}-package-manifest.json"
    if not package_manifest.is_file():
        package_manifest = Path(package["package_archive"]).with_name(f"{package['package_id']}-package-manifest.json")
    if not package_manifest.is_absolute():
        package_manifest = resolve_repo_path(package_manifest)
    if not package_archive.is_file():
        raise ValueError(f"package archive is missing: {package_archive}")
    if not package_manifest.is_file():
        raise ValueError(f"package manifest is missing: {package_manifest}")

    if args.key_scope == "peecos_production_release_key":
        if not args.private_key or not args.public_key or not args.passphrase_file:
            raise ValueError(
                "production signing requires --private-key, --public-key, and --passphrase-file"
            )
        private_key = resolve_repo_path(args.private_key)
        public_key = resolve_repo_path(args.public_key)
        passphrase_file = resolve_repo_path(args.passphrase_file)
        if REPO_ROOT in private_key.parents or private_key == REPO_ROOT:
            raise ValueError("production private key must not live inside the repository")
        if REPO_ROOT in passphrase_file.parents or passphrase_file == REPO_ROOT:
            raise ValueError("production passphrase file must not live inside the repository")
        if private_key.stat().st_mode & 0o077:
            raise ValueError("production private key permissions must not allow group/other access")
        if passphrase_file.stat().st_mode & 0o077:
            raise ValueError("production passphrase permissions must not allow group/other access")
    else:
        if args.private_key or args.public_key or args.passphrase_file:
            raise ValueError("explicit key paths require --key-scope peecos_production_release_key")
        private_key, public_key = ensure_dev_signing_key(key_dir=key_dir, openssl=openssl)
        passphrase_file = None
    release_dir = output_dir / args.release_id
    release_dir.mkdir(parents=True, exist_ok=True)
    checksums = release_dir / "SHA256SUMS"
    extra_artifacts = [resolve_repo_path(path) for path in args.extra_artifact]
    write_checksums(
        files=[
            package_archive,
            package_manifest,
            validation_result_path,
            *extra_artifacts,
        ],
        output=checksums,
    )
    signature = release_dir / "SHA256SUMS.sig"
    sign_file(
        openssl=openssl,
        private_key=private_key,
        file_to_sign=checksums,
        signature=signature,
        passphrase_file=passphrase_file,
    )
    verify_signature(
        openssl=openssl,
        public_key=public_key,
        file_to_verify=checksums,
        signature=signature,
    )
    signing_key: dict[str, Any] = {
        "key_type": "ed25519",
        "key_scope": args.key_scope,
        "public_key_path": str(public_key),
        "public_key_sha256": public_key_fingerprint(public_key),
    }
    if args.key_scope == "peecos_production_release_key":
        signing_key.update(
            {
                "private_key_path_recorded": False,
                "passphrase_path_recorded": False,
                "private_key_stored_in_repository": False,
                "private_key_stored_in_ignored_artifacts": False,
            }
        )
        boundaries = [
            "production release signing proof",
            "private key material outside repository",
            "not uploaded or published by this script",
            "no real owner data",
        ]
    else:
        signing_key.update(
            {
                "private_key_path": str(private_key),
                "private_key_stored_in_ignored_artifacts": True,
            }
        )
        boundaries = [
            "local development signing proof only",
            "not a peecos production release key",
            "not published",
            "no real owner data",
        ]

    proof = {
        "schema_version": "self_hosted_qemu_release_signing_proof_v1",
        "created_at": utc_now(),
        "status": "passed",
        "release_id": args.release_id,
        "signing_key": signing_key,
        "signed_file": str(checksums),
        "signature": str(signature),
        "signature_verified": True,
        "signed_artifacts": [
            package_archive.name,
            package_manifest.name,
            validation_result_path.name,
            *[path.name for path in extra_artifacts],
        ],
        "boundaries": boundaries,
    }
    proof_path = release_dir / "release-signing-proof.json"
    proof_path.write_text(json.dumps(proof, indent=2, sort_keys=True) + "\n")
    os.chmod(private_key, 0o600)
    print(json.dumps(proof, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
