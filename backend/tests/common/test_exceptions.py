import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import ValidationError
from sqlalchemy import exc as sa_exc
from sqlalchemy.orm.exc import FlushError

from app.core.exceptions import map_sa_exception, pg_detail, register_exception_handlers


class FakePGError(Exception):
    def __init__(self, pgcode: str | None = None):
        self.pgcode = pgcode


def _integrity(pgcode: str | None = None) -> sa_exc.IntegrityError:
    orig = FakePGError(pgcode)

    return sa_exc.IntegrityError("stmt", "params", orig)


@pytest.fixture
def client_with_handlers() -> TestClient:
    app = FastAPI()
    register_exception_handlers(app)

    @app.get("/raise/integrity")
    def raise_integrity():
        raise sa_exc.IntegrityError("stmt", "params", Exception("orig"))

    @app.get("/raise/data")
    def raise_data():
        raise sa_exc.DataError("stmt", "params", Exception("orig"))

    @app.get("/raise/flush")
    def raise_flush():
        raise FlushError("flush error")

    @app.get("/raise/operational")
    def raise_operational():
        raise sa_exc.OperationalError("stmt", "params", Exception("orig"))

    @app.get("/raise/dbapi")
    def raise_dbapi():
        raise sa_exc.DBAPIError("stmt", "params", Exception("orig"))

    @app.get("/raise/dbapi/invalidated")
    def raise_invalidated():
        e = sa_exc.DBAPIError("stmt", "params", Exception("orig"))
        e.connection_invalidated = True
        raise e

    @app.get("/raise/pydantic")
    def raise_pydantic():
        raise ValidationError.from_exception_data("ExampleModel", [])

    return TestClient(app)


class TestSQLAlchemyExceptionHandlers:
    def test_integrity_error(self, client_with_handlers):
        res = client_with_handlers.get("/raise/integrity")
        assert res.status_code == 409
        assert "detail" in res.json()
        assert "constraint" in res.json()["detail"].lower()

    def test_data_error(self, client_with_handlers):
        res = client_with_handlers.get("/raise/data")
        assert res.status_code == 400
        assert "detail" in res.json()

    def test_flush_error(self, client_with_handlers):
        res = client_with_handlers.get("/raise/flush")
        assert res.status_code == 400
        assert "detail" in res.json()

    def test_operational_error(self, client_with_handlers):
        res = client_with_handlers.get("/raise/operational")
        assert res.status_code == 503
        assert "detail" in res.json()

    def test_dbapi_error(self, client_with_handlers):
        res = client_with_handlers.get("/raise/dbapi")
        assert res.status_code == 500
        assert "detail" in res.json()

    def test_dbapi_error_invalidated(self, client_with_handlers):
        res = client_with_handlers.get("/raise/dbapi/invalidated")
        assert res.status_code == 503
        assert "detail" in res.json()


class TestPydanticValidationErrorHandler:
    def test_response_model_validation_error(self, client_with_handlers):
        res = client_with_handlers.get("/raise/pydantic")
        assert res.status_code == 500
        assert "detail" in res.json()
        assert "internal" in res.json()["detail"].lower()


class TestPgDetail:
    @pytest.mark.parametrize(
        "pgcode, expected",
        [
            ("23505", (409, "Duplicate resource (unique constraint).")),
            ("23503", (400, "Invalid reference (foreign key).")),
            ("23502", (400, "Missing required value (not-null constraint).")),
            (None, (409, "Constraint violation.")),
        ],
    )
    def test_pg_detail(self, pgcode, expected):
        assert pg_detail(_integrity(pgcode)) == expected


class TestMapSaException:
    @pytest.mark.parametrize(
        "exc, expected",
        [
            (_integrity("23505"), (409, "Duplicate resource (unique constraint).")),
            (
                sa_exc.DataError("s", "p", Exception("o")),
                (400, "Invalid data for a column."),
            ),
            (sa_exc.InvalidRequestError("x"), (400, "Invalid ORM operation or state.")),
            (FlushError("x"), (400, "Invalid ORM operation or state.")),
            (
                sa_exc.OperationalError("s", "p", Exception("o")),
                (503, "Database unavailable; try again."),
            ),
        ],
    )
    def test_map_sa_exception(self, exc, expected):
        assert map_sa_exception(exc) == expected

    def test_dbapi_error_500(self):
        e = sa_exc.DBAPIError("stmt", "params", Exception("orig"))
        assert map_sa_exception(e) == (500, "Database error.")

    def test_dbapi_error_connection_invalidated_503(self):
        e = sa_exc.DBAPIError("stmt", "params", Exception("orig"))
        e.connection_invalidated = True
        assert map_sa_exception(e) == (503, "Database error.")

    def test_unexpected_defaults_500(self):
        assert map_sa_exception(RuntimeError("boom")) == (
            500,
            "Unexpected server error.",
        )
