from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

FORBIDDEN_DIR_NAMES = {
    ".git",
    ".venv",
    "__pycache__",
    "bundles",
    "restore-proofs",
    "cdk.out",
    "node_modules",
}

FORBIDDEN_FILE_NAMES = {
    ".env",
    ".DS_Store",
}

FORBIDDEN_SUFFIXES = {
    ".key",
    ".pem",
    ".p12",
    ".pfx",
    ".log",
}

FORBIDDEN_TEXT_PATTERNS = {
    "aws_account_id": re.compile(r"\b\d{12}\b"),
    "aws_arn": re.compile(r"arn:aws:[A-Za-z0-9_:/+=,.@-]+"),
    "pilot_bucket": re.compile(r"pios-core-pilot-[a-z0-9-]+"),
    "aws_access_key": re.compile(r"\bA(KIA|SIA)[A-Z0-9]{16}\b"),
    "secret_field": re.compile(r'"secret"\s*:'),
    "private_key": re.compile(r"BEGIN (RSA |EC |OPENSSH |)PRIVATE KEY"),
}

REQUIRED_PATHS = {
    "bin/pios-core-init",
    "scripts/pios_core_init.py",
    "scripts/prove_self_hosted_core.py",
    "scripts/validate_core_bundle.py",
    "scripts/export_core_bundle.py",
    "schemas",
    "self-hosted-provisioning-manifest.example.json",
    "IMAGE_MANIFEST.json",
}


def should_skip_binary(path: Path) -> bool:
    return path.suffix.lower() in {
        ".png",
        ".jpg",
        ".jpeg",
        ".gif",
        ".webp",
        ".pdf",
        ".zst",
        ".gz",
        ".zip",
        ".tar",
    }


def relative(path: Path, root: Path) -> str:
    return str(path.relative_to(root))


def compiled_forbidden_patterns() -> dict[str, re.Pattern[str]]:
    patterns = dict(FORBIDDEN_TEXT_PATTERNS)
    extra_words = [
        item.strip()
        for item in os.environ.get("PIOS_IMAGE_ROOT_FORBIDDEN_WORDS", "").split(",")
        if item.strip()
    ]
    for index, word in enumerate(extra_words, start=1):
        patterns[f"deployment_specific_forbidden_word_{index}"] = re.compile(
            re.escape(word), re.IGNORECASE
        )
    return patterns


def scan_image_root(root: Path) -> dict[str, Any]:
    if not root.exists() or not root.is_dir():
        raise ValueError(f"image root does not exist or is not a directory: {root}")

    findings: list[dict[str, Any]] = []
    file_count = 0
    required_missing = [
        path for path in sorted(REQUIRED_PATHS) if not (root / path).exists()
    ]
    for missing in required_missing:
        findings.append(
            {
                "severity": "high",
                "kind": "missing_required_path",
                "path": missing,
            }
        )

    for path in sorted(root.rglob("*")):
        rel = relative(path, root)
        if path.is_dir():
            if path.name in FORBIDDEN_DIR_NAMES:
                findings.append(
                    {
                        "severity": "high",
                        "kind": "forbidden_directory",
                        "path": rel,
                    }
                )
            continue

        file_count += 1
        if path.name in FORBIDDEN_FILE_NAMES:
            findings.append(
                {
                    "severity": "high",
                    "kind": "forbidden_file_name",
                    "path": rel,
                }
            )
        if path.suffix in FORBIDDEN_SUFFIXES:
            findings.append(
                {
                    "severity": "high",
                    "kind": "forbidden_file_suffix",
                    "path": rel,
                }
            )
        if should_skip_binary(path):
            continue
        try:
            text = path.read_text(errors="replace")
        except OSError as exc:
            findings.append(
                {
                    "severity": "high",
                    "kind": "unreadable_file",
                    "path": rel,
                    "detail": str(exc),
                }
            )
            continue
        for name, pattern in compiled_forbidden_patterns().items():
            if name == "secret_field" and path.suffix == ".py":
                continue
            match = pattern.search(text)
            if match:
                findings.append(
                    {
                        "severity": "high",
                        "kind": "forbidden_text",
                        "pattern": name,
                        "path": rel,
                        "match": match.group(0)[:80],
                    }
                )

    return {
        "status": "passed" if not findings else "failed",
        "image_root": str(root),
        "file_count": file_count,
        "required_path_count": len(REQUIRED_PATHS),
        "finding_count": len(findings),
        "findings": findings,
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Validate that a self-hosted image root is data-empty and free of owner/deployment identifiers."
    )
    parser.add_argument("--image-root", required=True, type=Path)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    result = scan_image_root(args.image_root)
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
