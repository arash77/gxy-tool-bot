"""Find the tool directory a pull request works on, from its changed files.

A changed file belongs to the nearest folder above it that has a ``.shed.yml``
(planemo's rule for a tool repository), or, when no folder above it has one,
the nearest folder with a tool XML. Only folders with a tool XML count, so a
tool's own ``scripts/`` folder or a category folder is never returned.
The PR title's ``name:`` prefix only picks among those folders.
"""

from __future__ import annotations

import re
from pathlib import Path, PurePosixPath

SHED_FILES = (".shed.yml", ".shed.yaml")
_SAFE_PART = re.compile(r"^[A-Za-z0-9_-][A-Za-z0-9_.-]*$")
# XMLs that sit next to tools but are not tools themselves.
_NOT_TOOL_XML = re.compile(r"(.*macros.*|.*dependencies|datatypes_conf)\.xml$")


class ToolDirError(Exception):
    pass


def has_tool_xml(folder: Path) -> bool:
    return any(
        p.is_file() and not _NOT_TOOL_XML.match(p.name)
        for p in folder.glob("*.xml")
    )


def _owner(tools_dir: Path, rel: PurePosixPath) -> PurePosixPath | None:
    """The tool folder a changed path under tools_dir belongs to, or None."""
    # A removed file: start from the nearest folder that still exists.
    folders = [p for p in rel.parents if p != PurePosixPath(".")]
    folders = [p for p in folders if (tools_dir / p).is_dir()]
    for p in folders:
        if any((tools_dir / p / name).is_file() for name in SHED_FILES):
            return p if has_tool_xml(tools_dir / p) else None
    for p in folders:
        if has_tool_xml(tools_dir / p):
            return p
    return None


def _check_safe(tools_dir: Path, rel: PurePosixPath) -> None:
    if not all(_SAFE_PART.match(part) for part in rel.parts):
        raise ToolDirError(f"Refusing unsafe tool directory name: {rel}")
    walked = tools_dir
    for part in rel.parts:
        walked = walked / part
        if walked.is_symlink():
            raise ToolDirError(f"Refusing tools/{rel}: it goes through a symlink")
    if not walked.resolve().is_relative_to(tools_dir.resolve()):
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
        path = PurePosixPath(f.strip())
        if len(path.parts) < 2 or path.parts[0] != tools_prefix or ".." in path.parts:
            continue
        owner = _owner(tools_dir, PurePosixPath(*path.parts[1:]))
        if owner is not None:
            candidates.add(owner)

    if not candidates:
        raise ToolDirError("The PR changes no file in a tool folder under tools/")
    if len(candidates) > 1:
        name = title.split(":", 1)[0].strip() if ":" in title else ""
        picked = {c for c in candidates if name and (str(c) == name or c.name == name)}
        if len(picked) != 1:
            listed = ", ".join(sorted(f"tools/{c}" for c in candidates))
            raise ToolDirError(
                f"The PR changes several tool folders ({listed}); start the PR title "
                "with the one to work on, e.g. 'name: ...'"
            )
        candidates = picked
    (result,) = candidates
    _check_safe(tools_dir, result)
    return str(result)
