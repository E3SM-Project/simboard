def _make_sync_url(url: str) -> str:
    """Convert asyncpg connection string to psycopg (sync) for Alembic.

    Parameters:
    ----------
    url : str
        The asynchronous database URL.

    Returns:
    -------
    str
        The synchronous database URL.
    """
    if url.startswith("postgresql+asyncpg"):
        return url.replace("postgresql+asyncpg", "postgresql+psycopg")

    return url
