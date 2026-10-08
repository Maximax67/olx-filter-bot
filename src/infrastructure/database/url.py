from sqlalchemy.engine import make_url

_ASYNC_DRIVER = "postgresql+asyncpg"
_ACCEPTED_DRIVERS = frozenset({"postgres", "postgresql", _ASYNC_DRIVER})
_LIBPQ_ONLY_PARAMETERS = frozenset({"channel_binding"})


def normalize_database_url(raw: str) -> str:
    url = make_url(raw.strip())
    if url.drivername not in _ACCEPTED_DRIVERS:
        raise ValueError("database URL must use the postgresql scheme")

    query = {key: value for key, value in url.query.items() if key not in _LIBPQ_ONLY_PARAMETERS}
    sslmode = query.pop("sslmode", None)
    if sslmode is not None and "ssl" not in query:
        query["ssl"] = sslmode

    normalized = url.set(drivername=_ASYNC_DRIVER, query=query)
    return normalized.render_as_string(hide_password=False)
