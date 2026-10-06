"""Original performance directory persistence."""

import pytest
from sqlalchemy.exc import IntegrityError

from app.features.catalog.enums import SourceDirectoryKind
from app.features.catalog.models import SourceDirectory
from app.features.catalog.source_directories import persist_source_directory
from tests.features.catalog.test_models import (
    _create_case,
    _create_dependencies,
    _create_execution,
)


def test_source_directories_retain_distinct_paths_and_owners(db):
    user, machine, ingestion = _create_dependencies(db)
    case = _create_case(db, machine=machine)
    execution = _create_execution(
        db,
        case_id=case.id,
        ingestion_id=ingestion.id,
        user_id=user.id,
        execution_id="123.250101-000000",
    )
    for _ in range(2):
        persist_source_directory(db, case, SourceDirectoryKind.STAGING, "/staging/case")
        persist_source_directory(
            db, case, SourceDirectoryKind.ARCHIVE, "/archive/one/case"
        )
        persist_source_directory(
            db, case, SourceDirectoryKind.ARCHIVE, "/archive/two/case"
        )
        persist_source_directory(
            db, execution, SourceDirectoryKind.STAGING, "/staging/case/execution"
        )

    assert db.query(SourceDirectory).count() == 4
    assert len(case.source_directories) == 3
    assert len(execution.source_directories) == 1
    db.delete(case)
    db.flush()
    assert db.query(SourceDirectory).count() == 0


@pytest.mark.parametrize("both_owners", [False, True])
def test_source_directory_requires_exactly_one_owner(db, both_owners):
    user, machine, ingestion = _create_dependencies(db)
    case = _create_case(db, machine=machine)
    execution = _create_execution(
        db,
        case_id=case.id,
        ingestion_id=ingestion.id,
        user_id=user.id,
        execution_id="123.250101-000000",
    )
    with pytest.raises(IntegrityError), db.begin_nested():
        db.add(
            SourceDirectory(
                case_id=case.id if both_owners else None,
                execution_id=execution.id if both_owners else None,
                kind=SourceDirectoryKind.STAGING,
                path="/staging/case",
            )
        )
        db.flush()


def test_detail_responses_include_separate_source_directories(db):
    from app.features.catalog.api import (
        _case_detail_query,
        _case_to_detail_out,
        _execution_detail_query,
        _execution_to_out,
    )

    user, machine, ingestion = _create_dependencies(db)
    case = _create_case(db, machine=machine)
    execution = _create_execution(
        db,
        case_id=case.id,
        ingestion_id=ingestion.id,
        user_id=user.id,
        execution_id="123.250101-000000",
    )
    persist_source_directory(db, case, SourceDirectoryKind.STAGING, "/staging/case")
    persist_source_directory(
        db, execution, SourceDirectoryKind.ARCHIVE, "/archive/case/run"
    )
    db.expire_all()

    case_response = _case_to_detail_out(
        _case_detail_query(db).filter_by(id=case.id).one()
    ).model_dump(by_alias=True)
    execution_response = _execution_to_out(
        _execution_detail_query(db).filter_by(id=execution.id).one()
    ).model_dump(by_alias=True)
    assert [
        (item["kind"], item["path"]) for item in case_response["sourceDirectories"]
    ] == [("staging", "/staging/case")]
    assert [
        (item["kind"], item["path"]) for item in execution_response["sourceDirectories"]
    ] == [("archive", "/archive/case/run")]
    assert case_response["artifacts"] == []
    assert execution_response["artifacts"] == []
