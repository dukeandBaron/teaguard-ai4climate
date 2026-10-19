"""Package local, reviewable sources and evidence; exclude dynamic private records."""

import hashlib
import json
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main():
    acceptance = json.loads(
        (ROOT / "artifacts/ENGINEERING_ACCEPTANCE.json").read_text(encoding="utf-8")
    )
    if acceptance["status"] != "PASS_LOCAL_V3_ENGINEERING_ACCEPTANCE":
        raise ValueError("Acceptance is not PASS")
    for name, expected in acceptance["source_manifest"].items():
        if hashlib.sha256((ROOT / name).read_bytes()).hexdigest() != expected:
            raise ValueError("Source drift: " + name)
    pdf_receipt = json.loads(
        (ROOT / "artifacts/pdf_review/receipt.json").read_text(encoding="utf-8")
    )
    if pdf_receipt["visual_review"] != "PASS":
        raise ValueError("PDF visual review is incomplete")
    target = ROOT / "output/TeaGuard_Nature_V3_1_Local_Review.zip"
    files = []
    for path in ROOT.rglob("*"):
        if not path.is_file():
            continue
        relative = path.relative_to(ROOT)
        if any(
            part
            in (
                "__pycache__",
                ".ruff_cache",
                "local_records",
                "runtime",
                "engineering",
                "cli_tests",
                "evidence_tamper",
                ".git",
                "node_modules",
            )
            for part in relative.parts
        ):
            continue
        if relative.parts[0] == "output" and relative.parts[1] != "pdf":
            continue
        if relative.as_posix() in (
            "artifacts/PACKAGE_RECEIPT.json",
            "artifacts/runtime.json",
        ):
            continue
        if path.suffix in (".pyc", ".log", ".tmp") or path.name.startswith(".env"):
            continue
        files.append(path)
    manifest = {
        p.relative_to(ROOT).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
        for p in sorted(files)
    }
    with zipfile.ZipFile(target, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for path in sorted(files):
            archive.write(path, path.relative_to(ROOT).as_posix())
        archive.writestr(
            "PACKAGE_MEMBERS.json", json.dumps(manifest, ensure_ascii=False, indent=2)
        )
    with zipfile.ZipFile(target) as archive:
        if archive.testzip() is not None:
            raise ValueError("ZIP integrity failed")
        for name, expected in manifest.items():
            if hashlib.sha256(archive.read(name)).hexdigest() != expected:
                raise ValueError("ZIP member mismatch: " + name)
    receipt = {
        "status": "PASS_LOCAL_PACKAGE_INTEGRITY",
        "path": str(target),
        "bytes": target.stat().st_size,
        "members": len(manifest) + 1,
        "sha256": hashlib.sha256(target.read_bytes()).hexdigest(),
        "member_manifest": manifest,
        "dynamic_local_records_included": False,
        "uploaded": False,
    }
    (ROOT / "artifacts/PACKAGE_RECEIPT.json").write_text(
        json.dumps(receipt, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(
        json.dumps(
            {k: v for k, v in receipt.items() if k != "member_manifest"},
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
