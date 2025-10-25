from unittest.mock import MagicMock, patch

import pytest
from fastapi import HTTPException, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.common.dependencies import get_database_session
from app.core.database import transaction


class TestGetDb:
    def test_get_database_session(self):
        mock_session = MagicMock(spec=Session)

        with patch("app.common.dependencies.SessionLocal", return_value=mock_session):
            generator = get_database_session()
            db = next(generator)

            assert db == mock_session
            mock_session.close.assert_not_called()

            with pytest.raises(StopIteration):
                next(generator)

            mock_session.close.assert_called_once()


class TestTransaction:
    def test_transaction_commit(self):
        mock_session = MagicMock(spec=Session)

        with transaction(mock_session):
            mock_session.commit.assert_not_called()

        mock_session.commit.assert_called_once()
        mock_session.rollback.assert_not_called()

    def test_transaction_integrity_error(self):
        mock_session = MagicMock(spec=Session)
        mock_session.commit.side_effect = IntegrityError(
            "mock", "mock", Exception("mock")
        )

        with pytest.raises(HTTPException) as exc_info:
            with transaction(mock_session):
                pass

        assert exc_info.value.status_code == status.HTTP_409_CONFLICT
        assert (
            exc_info.value.detail
            == "Constraint violation while writing to the database."
        )
        mock_session.rollback.assert_called_once()

    def test_transaction_generic_exception(self):
        mock_session = MagicMock(spec=Session)
        mock_session.commit.side_effect = Exception("Generic error")

        with pytest.raises(Exception, match="Generic error"):
            with transaction(mock_session):
                pass

        mock_session.rollback.assert_called_once()
