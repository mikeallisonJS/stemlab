"""scripts/release.py: the bump inference and the version surgery around towncrier."""

import importlib.util
import json
import sys
from pathlib import Path

import pytest

_spec = importlib.util.spec_from_file_location("release", Path(__file__).parent.parent / "scripts" / "release.py")
release = importlib.util.module_from_spec(_spec)
sys.modules["release"] = release
_spec.loader.exec_module(release)


class TestFragmentType:
    def test_issue_names(self):
        assert release.fragment_type(Path("12.feature.md")) == "feature"
        assert release.fragment_type(Path("7.breaking.md")) == "breaking"
        assert release.fragment_type(Path("3.chore.md")) == "chore"

    def test_orphan_names(self):
        assert release.fragment_type(Path("+release-flow.chore.md")) == "chore"
        assert release.fragment_type(Path("+rocm-detect.bugfix.md")) == "bugfix"

    def test_rejects_unknown_type(self):
        assert release.fragment_type(Path("12.enhancement.md")) is None

    def test_rejects_missing_or_bad_prefix(self):
        assert release.fragment_type(Path("12.md")) is None
        assert release.fragment_type(Path("notes.txt")) is None
        assert release.fragment_type(Path("rename.feature.md")) is None
        assert release.fragment_type(Path("+Bad_Slug.feature.md")) is None


class TestNextVersion:
    def test_prerelease_releases_its_base_version(self):
        assert release.next_version("2.0.0.dev0", {"feature"}) == "2.0.0"
        assert release.next_version("2.0.0.dev3", {"breaking"}) == "2.0.0"
        assert release.next_version("2.0.0.dev0", {"chore"}) == "2.0.0"

    def test_bugfix_bumps_patch(self):
        assert release.next_version("2.0.0", {"bugfix"}) == "2.0.1"

    def test_feature_bumps_minor_and_resets_patch(self):
        assert release.next_version("2.0.3", {"feature", "bugfix"}) == "2.1.0"

    def test_breaking_bumps_major_from_one_point_oh(self):
        assert release.next_version("2.1.3", {"breaking", "feature"}) == "3.0.0"

    def test_breaking_rides_minor_while_zero_x(self):
        assert release.next_version("0.2.0", {"breaking"}) == "0.3.0"

    def test_hidden_types_still_bump_patch(self):
        assert release.next_version("2.0.0", {"chore", "docs"}) == "2.0.1"

    def test_rejects_unknown_shapes(self):
        with pytest.raises(SystemExit):
            release.next_version("2.0.0rc1", {"feature"})


class TestNpmVersion:
    def test_release_is_spelled_the_same(self):
        assert release.npm_version("2.0.0") == "2.0.0"

    def test_prerelease_uses_semver_suffix(self):
        assert release.npm_version("2.0.0.dev0") == "2.0.0-dev.0"


class TestWriteVersion:
    @pytest.fixture
    def tree(self, tmp_path, monkeypatch):
        pyproject = tmp_path / "pyproject.toml"
        pyproject.write_text(
            '[project]\nname = "stemlab"\nversion = "2.0.0.dev0"\n[tool.other]\nrequires = ["x>=1"]\n',
            encoding="utf-8",
        )
        init = tmp_path / "__init__.py"
        init.write_text('"""Stemlab."""\n\n__version__ = "2.0.0.dev0"\n', encoding="utf-8")
        package = tmp_path / "package.json"
        package.write_text(
            '{\n  "name": "stemlab-app",\n  "version": "2.0.0-dev.0",\n  "devDependencies": {\n    "vite": "^7.0.0"\n  }\n}\n',
            encoding="utf-8",
        )
        monkeypatch.setattr(release, "PYPROJECT", pyproject)
        monkeypatch.setattr(release, "INIT", init)
        monkeypatch.setattr(release, "PACKAGE_JSON", package)
        return tmp_path

    def test_writes_all_three_files(self, tree):
        release.write_version("2.0.0")
        assert 'version = "2.0.0"' in (tree / "pyproject.toml").read_text(encoding="utf-8")
        assert '__version__ = "2.0.0"' in (tree / "__init__.py").read_text(encoding="utf-8")
        package = json.loads((tree / "package.json").read_text(encoding="utf-8"))
        assert package["version"] == "2.0.0"
        assert package["devDependencies"] == {"vite": "^7.0.0"}  # dependency versions untouched

    def test_refuses_ambiguous_version_lines(self, tree):
        (tree / "pyproject.toml").write_text('version = "1"\nversion = "2"\n', encoding="utf-8")
        with pytest.raises(SystemExit):
            release.write_version("2.0.0")


class TestChangelogSection:
    def test_extracts_one_version(self, tmp_path, monkeypatch):
        changelog = tmp_path / "CHANGELOG.md"
        changelog.write_text(
            "# Changelog\n\n<!-- towncrier release notes start -->\n\n"
            "## v2.1.0 — 2026-11-01\n\n### Features\n\n- Newer thing\n\n\n"
            "## v2.0.0 — 2026-10-20\n\n### Features\n\n- First thing\n",
            encoding="utf-8",
        )
        monkeypatch.setattr(release, "CHANGELOG", changelog)
        assert release.changelog_section("2.0.0") == "### Features\n\n- First thing"
        assert release.changelog_section("2.1.0") == "### Features\n\n- Newer thing"
        with pytest.raises(SystemExit):
            release.changelog_section("1.0.0")


def test_repo_versions_agree():
    """The three real version lines must say the same thing, or a release bumps a lie."""
    current = release.current_version()
    assert f'__version__ = "{current}"' in release.INIT.read_text(encoding="utf-8")
    package = json.loads(release.PACKAGE_JSON.read_text(encoding="utf-8"))
    assert package["version"] == release.npm_version(current)
