from app.db.utils import _make_sync_url


class TestMakeSyncUrl:
    def test_make_sync_url_asyncpg(self):
        async_url = "postgresql+asyncpg://user:password@localhost/dbname"
        expected_sync_url = "postgresql+psycopg://user:password@localhost/dbname"

        assert _make_sync_url(async_url) == expected_sync_url

    def test_make_sync_url_non_asyncpg(self):
        sync_url = "postgresql+psycopg://user:password@localhost/dbname"

        assert _make_sync_url(sync_url) == sync_url
