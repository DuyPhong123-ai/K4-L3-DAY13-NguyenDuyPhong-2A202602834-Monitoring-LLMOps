from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
FORBIDDEN_TRACKED = {".env", "config/challenge.json", "data/logs.jsonl", "data/audit.jsonl"}
SECRET_PATTERNS = {
    "langfuse_secret": re.compile(r"sk-lf-[A-Za-z0-9_-]{20,}"),
    "langfuse_public": re.compile(r"pk-lf-[A-Za-z0-9_-]{20,}"),
    "generic_secret_assignment": re.compile(
        r"(?i)(?:api[_-]?key|secret[_-]?key|token)\s*[:=]\s*['\"]?[A-Za-z0-9_./+-]{20,}"
    ),
}
PII_PATTERNS = {
    "email": re.compile(r"(?<![\w.+-])[\w.+-]+@[\w-]+(?:\.[\w-]+)+(?![\w.-])"),
    "phone_vn": re.compile(r"(?<!\d)(?:\+84|84|0)(?:[ .-]?\d){9}(?!\d)"),
    "cccd": re.compile(r"(?<!\d)\d{3}(?:[ .-]?\d{3}){3}(?!\d)"),
    "credit_card": re.compile(r"(?<!\d)(?:\d[ -]?){12,18}\d(?!\d)"),
}


def candidate_files() -> list[str]:
    result = subprocess.run(
        ["git", "ls-files", "--cached", "--others", "--exclude-standard"],
        cwd=REPO_ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    return sorted(line.replace("\\", "/") for line in result.stdout.splitlines() if line)


def scan() -> list[str]:
    findings: list[str] = []
    files = candidate_files()
    for forbidden in sorted(FORBIDDEN_TRACKED.intersection(files)):
        findings.append(f"forbidden tracked/generated file: {forbidden}")
    for relative in files:
        path = REPO_ROOT / relative
        try:
            text = path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        for name, pattern in SECRET_PATTERNS.items():
            if pattern.search(text):
                findings.append(f"{name}: {relative}")
        if relative.startswith("submission/") and path.suffix.lower() in {".md", ".txt", ".json"}:
            pii_text = re.sub(r"(?i)\b[0-9a-f]{40}\b", "[GIT_SHA]", text)
            for name, pattern in PII_PATTERNS.items():
                if pattern.search(pii_text):
                    findings.append(f"raw {name} in submission: {relative}")
    return findings


def main() -> int:
    findings = scan()
    if findings:
        print("Security scan: FAIL")
        for finding in findings:
            print(f"- {finding}")
        return 1
    print("Security scan: PASS")
    print("- no committed .env, challenge, generated application log, or audit log")
    print("- no high-confidence secret pattern")
    print("- no raw email, VN phone, CCCD, or payment card in text evidence/report")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
