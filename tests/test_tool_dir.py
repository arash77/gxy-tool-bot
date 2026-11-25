"""Tests for finding a PR's tool folder from its changed files."""

from __future__ import annotations

from pathlib import Path

import pytest
from click.testing import CliRunner

from gxy_tool_bot.cli import cli
from gxy_tool_bot.tool_dir import ToolDirError, find_tool_dir


def _tool(root: Path, rel: str, shed: str | None = ".shed.yml", xml: str = "tool.xml") -> None:
    d = root / rel
    d.mkdir(parents=True, exist_ok=True)
    (d / xml).write_text("<tool/>")
    if shed:
        (d / shed).write_text("name: x\n")


@pytest.fixture
def tools(tmp_path: Path) -> Path:
    t = tmp_path / "tools"
    _tool(t, "samblaster", shed=".shed.yaml")
    _tool(t, "image_processing/imagej2", xml="imagej2_crop.xml")
    (t / "image_processing/imagej2/imagej2_macros.xml").write_text("<macros/>")
    (t / "image_processing/imagej2/test-data").mkdir()
    _tool(t, "image_processing/yolo-utils/doclayoutyolo")
    _tool(t, "text_processing/text_processing")
    _tool(t, "EDeN/EDeN", shed=None)
    _tool(t, "music_deconvolution")
    (t / "music_deconvolution/scripts").mkdir()
    (t / "music_deconvolution/scripts/helper.xml").write_text("<tool/>")
    # A suite: shed file, no tool XML of its own.
    (t / "rna_tools/kinwalker").mkdir(parents=True)
    (t / "rna_tools/kinwalker/.shed.yml").write_text("name: kinwalker\n")
    (t / "rna_tools/kinwalker/README.md").write_text("")
    (t / "rna_tools/README.md").write_text("")
    return t


@pytest.mark.parametrize("changed, expected", [
    (["tools/samblaster/samblaster.xml"], "samblaster"),
    (["tools/samblaster/test-data/a.bam"], "samblaster"),
    (["tools/image_processing/imagej2/imagej2_crop.xml"], "image_processing/imagej2"),
    (["tools/image_processing/imagej2/test-data/new.png"], "image_processing/imagej2"),
    (["tools/image_processing/yolo-utils/doclayoutyolo/tool.xml"],
     "image_processing/yolo-utils/doclayoutyolo"),
    (["tools/text_processing/text_processing/tool.xml"], "text_processing/text_processing"),
    (["tools/EDeN/EDeN/tool.xml"], "EDeN/EDeN"),
    # A tool's own subfolder belongs to the tool, even with an XML in it.
    (["tools/music_deconvolution/scripts/helper.xml"], "music_deconvolution"),
    # A removed file counts from the nearest folder that is still there.
    (["tools/image_processing/imagej2/gone/old.xml"], "image_processing/imagej2"),
    # Files outside tool folders are ignored.
    ([".github/workflows/ci.yml", "README.md", "tools/rna_tools/README.md",
      "tools/samblaster/samblaster.xml"], "samblaster"),
])
def test_finds_tool_dir(tools: Path, changed: list[str], expected: str) -> None:
    assert find_tool_dir(tools, changed) == expected


@pytest.mark.parametrize("changed", [
    [],
    [".github/workflows/ci.yml"],
    ["tools/rna_tools/README.md"],            # category folder
    ["tools/rna_tools/kinwalker/README.md"],  # suite without a tool XML
    ["tools/../etc/passwd"],
])
def test_no_tool_dir(tools: Path, changed: list[str]) -> None:
    with pytest.raises(ToolDirError, match="no file in a tool folder"):
        find_tool_dir(tools, changed)


def test_title_picks_among_several(tools: Path) -> None:
    changed = ["tools/samblaster/samblaster.xml",
               "tools/image_processing/imagej2/imagej2_crop.xml"]
    assert find_tool_dir(tools, changed, "imagej2: update fiji") == "image_processing/imagej2"
    title = "image_processing/imagej2: x"
    assert find_tool_dir(tools, changed, title) == "image_processing/imagej2"
    with pytest.raises(ToolDirError, match="several tool folders"):
        find_tool_dir(tools, changed, "Update fiji and samblaster")
    with pytest.raises(ToolDirError, match="several tool folders"):
        find_tool_dir(tools, changed, "flye: not among the changed ones")


def test_title_never_adds_a_folder(tools: Path) -> None:
    # One changed tool: the title can't redirect the bot elsewhere.
    assert find_tool_dir(tools, ["tools/samblaster/samblaster.xml"], "imagej2: x") == "samblaster"


def test_prose_title_uses_changed_files(tools: Path) -> None:
    changed = ["tools/image_processing/imagej2/imagej2_crop.xml"]
    assert find_tool_dir(tools, changed, "Update fiji launcher") == "image_processing/imagej2"


def test_refuses_symlinked_folder(tools: Path, tmp_path: Path) -> None:
    outside = tmp_path / "outside"
    _tool(outside, "evil")
    (tools / "linked").symlink_to(outside)
    with pytest.raises(ToolDirError, match="symlink"):
        find_tool_dir(tools, ["tools/linked/evil/tool.xml"])


def test_refuses_unsafe_name(tools: Path) -> None:
    _tool(tools, "bad name")
    with pytest.raises(ToolDirError, match="unsafe"):
        find_tool_dir(tools, ["tools/bad name/tool.xml"])


def test_cli_prints_only_the_path(tools: Path, tmp_path: Path) -> None:
    changed = tmp_path / "changed.txt"
    changed.write_text("tools/image_processing/imagej2/imagej2_crop.xml\n")
    result = CliRunner().invoke(cli, ["find-tool-dir", "--changed-files", str(changed),
                                      "--title", "imagej2: x", "--tools-dir", str(tools)])
    assert result.exit_code == 0, result.output
    assert result.output == "image_processing/imagej2\n"


def test_cli_fails_with_message(tools: Path, tmp_path: Path) -> None:
    changed = tmp_path / "changed.txt"
    changed.write_text("README.md\n")
    result = CliRunner().invoke(cli, ["find-tool-dir", "--changed-files", str(changed),
                                      "--tools-dir", str(tools)])
    assert result.exit_code == 1
    assert "no file in a tool folder" in result.output
