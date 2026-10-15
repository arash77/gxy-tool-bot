"""Shared utility helpers used across multiple modules."""

from __future__ import annotations

import logging
import os
import re
from pathlib import Path

logger = logging.getLogger(__name__)

# Environment variables are treated as credentials when any
# underscore/dash-delimited name component matches a marker — this catches
# AWS_ACCESS_KEY_ID and DOCKER_AUTH_CONFIG while leaving ordinary config vars
# like GITHUB_SERVER_URL, PIP_INDEX_URL, and PYTHON_KEYRING_BACKEND alone.
_SECRET_ENV_COMPONENTS = {
    "TOKEN", "KEY", "APIKEY", "SECRET", "PASSWORD", "PASSWD",
    "CREDENTIAL", "CREDENTIALS", "AUTH", "DSN",
}


def _is_sensitive_env_name(name: str) -> bool:
    components = re.split(r"[_\-.]+", name.upper())
    return any(part in _SECRET_ENV_COMPONENTS for part in components)


def sanitized_env(extra_names: set[str] | None = None) -> dict[str, str]:
    """Copy of the process environment minus credential-looking variables.

    ``extra_names`` are additional variable names to drop unconditionally —
    e.g. the configured LLM API key env var, whose name need not contain a
    credential marker.
    """
    extra = {n.upper() for n in (extra_names or ())}
    return {
        k: v for k, v in os.environ.items()
        if not _is_sensitive_env_name(k) and k.upper() not in extra
    }


# CI report artifact names (lowercase substring match). Keep to names CI
# actually produces — a bare "test" keyword also matched e.g.
# 'gitignored-test-data', a binary zip of test files whose contents then got
# dumped into the prompt.
_ARTIFACT_NAME_KEYWORDS = ("lint", "test result", "tool test output", "file size")


def is_report_artifact(name: str) -> bool:
    """Whether a GitHub Actions artifact looks like a CI report worth downloading."""
    return any(kw in name.lower() for kw in _ARTIFACT_NAME_KEYWORDS)


# Caps on CI artifact text inlined into agent prompts. Planemo reports embed
# full expected-vs-actual diffs (in both tool_test_output.json output_problems
# and tool_test_output.md) and have produced ~2.4M-char prompts that the chat
# endpoint rejects with HTTP 400. The total cap matches the default context
# budget (api.max_context_chars = 100_000) — reports must share that budget
# with the rest of the prompt rather than exhaust it.
_ARTIFACT_FILE_CHAR_CAP = 50_000
_ARTIFACT_TOTAL_CHAR_CAP = 100_000


def _truncate_text(text: str, cap: int) -> str:
    if len(text) <= cap:
        return text
    return text[:cap] + f"\n[... truncated, {len(text)} chars total ...]"


def collect_ci_artifacts(gh, pr_number: int) -> dict[str, str]:
    """Download CI report artifacts for a PR; return "artifact/file" -> text.

    Shared by the feedback and review flows. Only artifacts matching
    ``is_report_artifact`` are downloaded; when the combined 'All tool test
    results' artifact exists, the redundant per-chunk 'Tool test output N'
    artifacts are skipped. HTML reports are dropped as too verbose, and in
    test-result artifacts the ``.md`` report is dropped when a ``.json`` is
    present — planemo-ci-action generates the markdown as a rendered
    duplicate of the JSON (for $GITHUB_STEP_SUMMARY), so it adds no
    information. Planemo test JSON is itself reduced to a failure summary.
    File contents are bounded per file and in total so oversized reports
    cannot overflow the LLM context window.
    """
    # Imported here to keep this module's top-level imports dependency-free.
    from gxy_tool_bot.planemo_utils import summarize_test_json

    ci_artifacts: dict[str, str] = {}
    total_chars = 0
    try:
        artifacts = gh.get_pr_artifacts(pr_number)

        # If the combined test results artifact exists, skip per-chunk artifacts
        # since the combined one already contains all test results.
        has_combined = any(a["name"] == "All tool test results" for a in artifacts)

        for artifact in artifacts:
            name = artifact["name"]
            # Only download artifacts that look like CI reports
            if not is_report_artifact(name):
                continue
            # Skip per-chunk test artifacts if combined results are available
            if has_combined and name.startswith("Tool test output "):
                continue
            files = gh.download_artifact(artifact["id"])
            # planemo-ci-action emits tool_test_output.md/html as rendered
            # duplicates of tool_test_output.json — skip them when the JSON
            # is present since they carry no additional information.
            has_test_json = "test" in name.lower() and any(
                f.endswith(".json") for f in files
            )
            for fname in sorted(files):
                content = files[fname]
                # Skip HTML reports — too verbose for LLM context
                if fname.endswith(".html"):
                    continue
                if has_test_json and fname.endswith(".md"):
                    continue
                try:
                    text = content.decode("utf-8")
                except UnicodeDecodeError:
                    text = content.decode("utf-8", errors="replace")
                # Parse planemo test JSON into a compact summary of failures
                if fname.endswith(".json") and "test" in name.lower():
                    text = summarize_test_json(text)
                key = f"{name}/{fname}"
                remaining = _ARTIFACT_TOTAL_CHAR_CAP - total_chars
                if remaining <= 0:
                    ci_artifacts[key] = "[omitted — CI artifact size cap reached]"
                    continue
                text = _truncate_text(text, min(_ARTIFACT_FILE_CHAR_CAP, remaining))
                total_chars += len(text)
                ci_artifacts[key] = text
    except Exception:
        logger.warning("Failed to fetch CI artifacts", exc_info=True)
    return ci_artifacts


def read_tool_files(tool_dir: Path) -> dict[str, str]:
    """Read all files from a tool directory, returning relative path -> content.

    Skips internal files like ``.tool-name``. Other dotfiles such as
    ``.agent-notes`` are included — the review flow uses them to understand
    the writer's rationale. Binary files are skipped (listed as a placeholder)
    so the bot knows they exist without getting corrupted text in its context.

    Used by both the feedback flow (``_collect_feedback``) and the review flow
    (``collect_review_context``) to gather existing tool files.
    """
    files: dict[str, str] = {}
    if not tool_dir.exists():
        return files
    for f in tool_dir.rglob("*"):
        if f.is_file():
            rel = f.relative_to(tool_dir)
            # Skip internal files
            if rel.name == ".tool-name":
                continue
            try:
                files[str(rel)] = f.read_text(encoding="utf-8")
            except (UnicodeDecodeError, OSError):
                # Binary file — include a placeholder so the bot knows it exists
                # but doesn't try to read/write it as text.
                files[str(rel)] = f"[binary file — {f.stat().st_size} bytes — use track_file to include in PR]"
    return files
