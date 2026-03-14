import gzip

from app.features.ingestion.parsers.utils import _get_open_func, _open_text


class TestParserUtils:
    def test_open_text_reads_plain_file(self, tmp_path):
        file_path = tmp_path / "plain.txt"
        file_path.write_text("plain text")

        assert _open_text(file_path) == "plain text"

    def test_open_text_reads_gz_file(self, tmp_path):
        file_path = tmp_path / "plain.txt.gz"
        with gzip.open(file_path, "wt", encoding="utf-8") as f:
            f.write("gz text")

        assert _open_text(file_path) == "gz text"

    def test_get_open_func_returns_gzip_open_for_gz(self):
        assert _get_open_func("file.txt.gz") is gzip.open

    def test_get_open_func_returns_open_for_plain_file(self):
        assert _get_open_func("file.txt") is open
