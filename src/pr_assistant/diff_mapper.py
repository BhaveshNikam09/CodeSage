import re
from typing import Dict, List, Optional


HUNK_RE = re.compile(r"@@ -(?P<old_start>\d+)(?:,\d+)? \+(?P<new_start>\d+)(?:,\d+)? @@")


def map_patch_lines(patch: str) -> Dict[int, Dict]:
    """Map changed new-file lines to GitHub diff positions."""
    mapping = {}
    old_line = None
    new_line = None
    position = 0

    for raw_line in (patch or "").splitlines():
        header = HUNK_RE.match(raw_line)
        if header:
            old_line = int(header.group("old_start"))
            new_line = int(header.group("new_start"))
            position = 0
            continue

        if old_line is None or new_line is None:
            continue

        position += 1
        if raw_line.startswith("+") and not raw_line.startswith("+++"):
            mapping[new_line] = {
                "line": new_line,
                "position": position,
                "side": "RIGHT",
                "change": "added",
            }
            new_line += 1
            continue

        if raw_line.startswith("-") and not raw_line.startswith("---"):
            old_line += 1
            continue

        mapping[new_line] = {
            "line": new_line,
            "position": position,
            "side": "RIGHT",
            "change": "context",
        }
        old_line += 1
        new_line += 1

    return mapping


def nearest_diff_line(line: int, mapping: Dict[int, Dict]) -> Optional[Dict]:
    """Find the nearest reviewable changed/context line in a patch."""
    if not mapping:
        return None
    if line in mapping:
        return mapping[line]

    changed_lines = sorted(mapping)
    closest = min(changed_lines, key=lambda candidate: abs(candidate - line))
    if abs(closest - line) <= 3:
        return mapping[closest]
    return None


def changed_file_payload(file_info: Dict, content: str) -> Dict:
    mapping = map_patch_lines(file_info.get("patch", ""))
    return {
        "filename": file_info.get("filename", ""),
        "status": file_info.get("status", "modified"),
        "sha": file_info.get("sha", ""),
        "patch": file_info.get("patch", ""),
        "changed_lines": sorted(mapping),
        "line_mapping": mapping,
        "content": content,
    }


def build_reviewable_files(files: List[Dict], contents_by_file: Dict[str, str]) -> List[Dict]:
    reviewable = []
    for file_info in files:
        filename = file_info.get("filename", "")
        if not filename or file_info.get("status") == "removed":
            continue
        content = contents_by_file.get(filename, "")
        if not content:
            continue
        reviewable.append(changed_file_payload(file_info, content))
    return reviewable
