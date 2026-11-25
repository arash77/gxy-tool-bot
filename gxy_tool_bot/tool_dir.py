"""Find the tool directory a pull request works on, from its changed files.

A changed file belongs to the nearest folder above it that has a ``.shed.yml``
(planemo's rule for a tool repository) and a tool XML; otherwise to the nearest
folder below that (or anywhere above the file, when there is no shed file) with
a tool XML. A tool XML is one whose root element is ``<tool>``, so a tool's own
``test-data/`` or ``scripts/`` folder, a category folder or an empty suite is
never returned. The PR title's ``name:`` prefix only picks among those folders.
"""

from __future__ import annotations

import re
from pathlib import Path, PurePosixPath

SHED_FILES = (".shed.yml", ".shed.yaml")
_SAFE_PART = re.compile(r"^[A-Za-z0-9_-][A-Za-z0-9_.-]*$")
# What may come before the root element: XML declaration, comments, doctype.
_PROLOG = re.compile(r"\s*(<\?.*?\?>|<!--.*?-->|<!DOCTYPE[^>]*>)", re.S)
_TOOL_ROOT = re.compile(r"\s*<tool[\s/>]")


class ToolDirError(Exception):
    pass


def _is_tool_xml(path: Path) -> bool:
    """Whether the root element is <tool>. Matched as text, not parsed: these
    are PR files, and only the first element matters."""
    try:
        with open(path, encoding="utf-8-sig", errors="replace") as f:
            head = f.read(65536)
    except OSError:
        return False
    pos = 0
    while m := _PROLOG.match(head, pos):
        pos = m.end()
    return _TOOL_ROOT.match(head, pos) is not None


def has_tool_xml(folder: Path) -> bool:
    return any(p.is_file() and _is_tool_xml(p) for p in folder.glob("*.xml"))


def _owner(tools_dir: Path, rel: PurePosixPath) -> PurePosixPath | None:
    """The tool folder a changed path under tools_dir belongs to, or None."""
    # Nearest first. A removed file counts from the nearest folder still there.
    folders = [p for p in rel.parents if p != PurePosixPath(".") and (tools_dir / p).is_dir()]
    shed = next((i for i, p in enumerate(folders)
                 if any((tools_dir / p / name).is_file() for name in SHED_FILES)), None)
    if shed is not None and has_tool_xml(tools_dir / folders[shed]):
        return folders[shed]
    # No shed file, or one on a suite folder without tools of its own: the
    # nearest tool folder below it.
    for p in folders[:shed]:
        if has_tool_xml(tools_dir / p):
            return p
    return None


def _check_safe(tools_dir: Path, rel: PurePosixPath) -> None:
    if not all(_SAFE_PART.match(part) for part in rel.parts):
        raise ToolDirError(f"Refusing unsafe tool directory name: {rel}")
    paths = [tools_dir]
    for part in rel.parts:
        paths.append(paths[-1] / part)
    if any(p.is_symlink() for p in paths):
        raise ToolDirError(f"Refusing tools/{rel}: it goes through a symlink")
    if not paths[-1].resolve().is_relative_to(tools_dir.resolve()):
        raise ToolDirError(f"Refusing tools/{rel}: it is outside the tools folder")


def find_tool_dir(tools_dir: Path, changed_files: list[str], title: str = "",
                  tools_prefix: str = "tools") -> str:
    """Return the tool folder (relative to tools_dir) the changed files touch.

    changed_files are repo-relative paths; only those under tools_prefix count.
    Raises ToolDirError when there is none, or several and the title's
    ``name:`` prefix doesn't pick exactly one.
    """
    candidates: set[PurePosixPath] = set()
    for f in changed_files:
        path = PurePosixPath(f)
        if len(path.parts) < 2 or path.parts[0] != tools_prefix or ".." in path.parts:
            continue
        owner = _owner(tools_dir, PurePosixPath(*path.parts[1:]))
        if owner is not None:
            candidates.add(owner)

    if not candidates:
        raise ToolDirError("The PR changes no file in a tool folder under tools/")
    if len(candidates) > 1:
        name = title.split(":", 1)[0].strip().strip("/") if ":" in title else ""
        name = name.removeprefix(f"{tools_prefix}/")
        picked = {c for c in candidates if name and (str(c) == name or c.name == name)}
        if len(picked) != 1:
            listed = ", ".join(sorted(str(c) for c in candidates))
            raise ToolDirError(
                f"The PR changes several tool folders under tools/ ({listed}); start the "
                "PR title with the one to work on, e.g. '<folder>: ...'"
            )
        candidates = picked
    (result,) = candidates
    _check_safe(tools_dir, result)
    return str(result)
