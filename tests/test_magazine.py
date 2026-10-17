from pathlib import Path
from zipfile import ZipFile

from magger.magazine import build_epub


def test_build_epub_includes_summary_and_source_link(tmp_path: Path):
    target = tmp_path / "issue.epub"
    build_epub([{
        "title": "Useful Article", "url": "https://example.com/story", "feed": "Example Feed",
        "published": "2026-10-16T10:00:00+00:00", "topic": "Technology",
        "editorial_summary": "A concise and faithful summary.", "rationale": "Original reporting.",
    }], {"title": "Test Mag"}, target)
    assert target.is_file() and target.stat().st_size > 0
    with ZipFile(target) as archive:
        text = b"".join(archive.read(name) for name in archive.namelist() if name.endswith(".xhtml")).decode("utf-8")
    assert "Useful Article" in text
    assert "A concise and faithful summary." in text
    assert "https://example.com/story" in text
