from pathlib import Path

from agent_safe_write import fingerprint, safe_write


target = Path("example-config.txt")
if not target.exists():
    target.write_text("feature=false\n")

before = fingerprint(target)
receipt = safe_write(
    target,
    b"feature=true\n",
    expected_sha256=before.sha256,
    allowed_root=Path.cwd(),
)
print(receipt.to_json())
