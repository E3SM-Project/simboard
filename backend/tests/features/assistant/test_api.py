from uuid import UUID, uuid4

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.version import API_BASE
from app.core.config import settings
from app.features.assistant import api as assistant_api
from app.features.assistant.schemas import SimulationSummaryResponse
from app.features.ingestion.enums import IngestionSourceType, IngestionStatus
from app.features.ingestion.models import Ingestion
from app.features.machine.models import Machine
from app.features.simulation.models import Case, Simulation
from app.features.user.manager import current_active_user
from app.features.user.models import User, UserRole
from app.main import app


@pytest.fixture
def authenticated_client(async_client: AsyncClient, normal_user):
    def fake_current_user():
        return User(
            id=UUID(normal_user["id"]),
            email=normal_user["email"],
            is_active=True,
            is_verified=True,
            role=UserRole.USER,
        )

    app.dependency_overrides[current_active_user] = fake_current_user
    return async_client


async def _create_case(db: AsyncSession, name: str = "assistant_api_case") -> Case:
    case = Case(name=name)
    db.add(case)
    await db.flush()
    return case


async def _create_simulation(
    db: AsyncSession,
    normal_user: dict[str, str],
    admin_user: dict[str, str],
    *,
    execution_id: str = "assistant-api-exec-1",
) -> Simulation:
    machine = (await db.execute(select(Machine))).scalars().first()
    assert machine is not None

    case = await _create_case(db)
    ingestion = Ingestion(
        source_type=IngestionSourceType.BROWSER_UPLOAD,
        source_reference=execution_id,
        machine_id=machine.id,
        triggered_by=UUID(normal_user["id"]),
        status=IngestionStatus.SUCCESS,
        created_count=1,
        duplicate_count=0,
        error_count=0,
    )
    db.add(ingestion)
    await db.flush()

    simulation = Simulation(
        case_id=case.id,
        execution_id=execution_id,
        compset="AQUAPLANET",
        compset_alias="QPC4",
        grid_name="f19_f19",
        grid_resolution="1.9x2.5",
        simulation_type="experimental",
        status="completed",
        initialization_type="startup",
        machine_id=machine.id,
        simulation_start_date="2023-01-01T00:00:00Z",
        git_tag="v2.0.0",
        created_by=UUID(normal_user["id"]),
        last_updated_by=UUID(admin_user["id"]),
        ingestion_id=ingestion.id,
    )
    db.add(simulation)
    await db.flush()
    case.reference_simulation_id = simulation.id
    await db.commit()
    await db.refresh(simulation)
    return simulation


class TestSummarizeSimulationEndpoint:
    @pytest.fixture(autouse=True)
    def _force_deterministic(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(settings, "assistant_llm_enabled", False)

    @pytest.mark.asyncio
    async def test_authenticated_request_returns_summary_contract(
        self,
        authenticated_client: AsyncClient,
        async_db: AsyncSession,
        normal_user,
        admin_user,
    ) -> None:
        simulation = await _create_simulation(
            async_db,
            normal_user,
            admin_user,
        )

        response = await authenticated_client.post(
            f"{API_BASE}/simulations/{simulation.id}/summary"
        )

        assert response.status_code == 200
        data = response.json()
        assert (
            "Simulation assistant-api-exec-1 belongs to case assistant_api_case."
            in data["answer"]
        )
        assert isinstance(data["citations"], list)
        assert data["assumptions"] == []
        assert isinstance(data["caveats"], list)
        assert data["limitations"] == [
            "This summary uses only metadata already stored in SimBoard. It does not use retrieval, diagnostics interpretation, or LLM reasoning."
        ]
        assert isinstance(data["suggestedFollowups"], list)
        assert UUID(data["traceId"])
        assert {citation["path"] for citation in data["citations"]} >= {
            "simulation.execution_id",
            "case.name",
        }

    @pytest.mark.asyncio
    async def test_unauthenticated_request_returns_401(
        self,
        async_client: AsyncClient,
        async_db: AsyncSession,
        normal_user,
        admin_user,
    ) -> None:
        simulation = await _create_simulation(
            async_db,
            normal_user,
            admin_user,
        )

        response = await async_client.post(
            f"{API_BASE}/simulations/{simulation.id}/summary"
        )

        assert response.status_code == 401
        assert response.json() == {"detail": "Not authenticated"}

    @pytest.mark.asyncio
    async def test_unknown_simulation_returns_404(
        self, authenticated_client: AsyncClient
    ) -> None:
        response = await authenticated_client.post(
            f"{API_BASE}/simulations/{uuid4()}/summary"
        )

        assert response.status_code == 404
        assert response.json() == {"detail": "Simulation not found"}


class _FakeScalarResult:
    def __init__(self, simulation) -> None:
        self._simulation = simulation

    def unique(self):
        return self

    def one_or_none(self):
        return self._simulation


class _FakeExecuteResult:
    def __init__(self, simulation) -> None:
        self._simulation = simulation

    def scalars(self):
        return _FakeScalarResult(self._simulation)


class _FakeAsyncSession:
    def __init__(self, simulation) -> None:
        self._simulation = simulation

    async def execute(self, stmt):
        self.statement = stmt
        return _FakeExecuteResult(self._simulation)


class TestSummarizeSimulationUnit:
    @pytest.mark.asyncio
    async def test_summarize_simulation_returns_generation_summary(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        sim_id = uuid4()
        trace_id = uuid4()
        user = User(
            id=uuid4(),
            email="user@example.com",
            is_active=True,
            is_verified=True,
            role=UserRole.USER,
        )
        db = _FakeAsyncSession(type("SimulationStub", (), {"id": sim_id})())
        summary = SimulationSummaryResponse(
            answer="Deterministic assistant summary.",
            citations=[],
            assumptions=[],
            caveats=[],
            limitations=["limit"],
            suggested_followups=["follow up"],
            generation_mode="deterministic",
            generation_provider=None,
            generation_model=None,
            trace_id=uuid4(),
        )
        logged: list[tuple[str, tuple[object, ...]]] = []

        async def fake_generate(simulation):
            assert simulation.id == sim_id
            return type(
                "GenerationResult",
                (),
                {
                    "summary": summary,
                    "fallback_reason": None,
                    "llm_latency_ms": 12.5,
                    "attempted_provider": "livai",
                    "attempted_model": "livai-model",
                },
            )()

        monkeypatch.setattr(assistant_api, "generate_simulation_summary", fake_generate)
        monkeypatch.setattr(assistant_api, "uuid4", lambda: trace_id)
        monkeypatch.setattr(
            assistant_api.logger,
            "info",
            lambda message, *args: logged.append((message, args)),
        )

        response = await assistant_api.summarize_simulation(sim_id, db=db, user=user)

        assert response.answer == "Deterministic assistant summary."
        assert response.trace_id == trace_id
        assert logged
        assert "success=true" in logged[0][0]
        assert "llm_success=%s" in logged[0][0]
        assert "fallback_used=%s" in logged[0][0]
        assert logged[0][1][0] == trace_id
        assert logged[0][1][1] == sim_id
        assert logged[0][1][2] == user.id
        assert logged[0][1][3] == "false"
        assert logged[0][1][4] == "false"

    @pytest.mark.asyncio
    async def test_summarize_simulation_logs_true_fallback_when_llm_attempt_fails(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        sim_id = uuid4()
        trace_id = uuid4()
        user = User(
            id=uuid4(),
            email="user@example.com",
            is_active=True,
            is_verified=True,
            role=UserRole.USER,
        )
        db = _FakeAsyncSession(type("SimulationStub", (), {"id": sim_id})())
        summary = SimulationSummaryResponse(
            answer="Deterministic fallback summary.",
            citations=[],
            assumptions=[],
            caveats=[],
            limitations=["limit"],
            suggested_followups=["follow up"],
            generation_mode="deterministic",
            generation_provider=None,
            generation_model=None,
            trace_id=uuid4(),
        )
        logged: list[tuple[str, tuple[object, ...]]] = []

        async def fake_generate(simulation):
            assert simulation.id == sim_id
            return type(
                "GenerationResult",
                (),
                {
                    "summary": summary,
                    "fallback_reason": "ModelHTTPError",
                    "llm_latency_ms": 12.5,
                    "attempted_provider": "ollama",
                    "attempted_model": "gemma4:3b",
                },
            )()

        monkeypatch.setattr(assistant_api, "generate_simulation_summary", fake_generate)
        monkeypatch.setattr(assistant_api, "uuid4", lambda: trace_id)
        monkeypatch.setattr(
            assistant_api.logger,
            "info",
            lambda message, *args: logged.append((message, args)),
        )

        response = await assistant_api.summarize_simulation(sim_id, db=db, user=user)

        assert response.answer == "Deterministic fallback summary."
        assert response.trace_id == trace_id
        assert logged
        assert "success=true" in logged[0][0]
        assert "llm_success=%s" in logged[0][0]
        assert "fallback_used=%s" in logged[0][0]
        assert logged[0][1][3] == "false"
        assert logged[0][1][4] == "true"

    @pytest.mark.asyncio
    async def test_summarize_simulation_returns_ollama_generation_metadata(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        sim_id = uuid4()
        trace_id = uuid4()
        user = User(
            id=uuid4(),
            email="user@example.com",
            is_active=True,
            is_verified=True,
            role=UserRole.USER,
        )
        db = _FakeAsyncSession(type("SimulationStub", (), {"id": sim_id})())
        summary = SimulationSummaryResponse(
            answer="LLM assistant summary.",
            citations=[],
            assumptions=[],
            caveats=[],
            limitations=["limit"],
            suggested_followups=["follow up"],
            generation_mode="llm",
            generation_provider="ollama",
            generation_model="gemma4:26b",
            trace_id=uuid4(),
        )
        logged: list[tuple[str, tuple[object, ...]]] = []

        async def fake_generate(simulation):
            assert simulation.id == sim_id
            return type(
                "GenerationResult",
                (),
                {
                    "summary": summary,
                    "fallback_reason": None,
                    "llm_latency_ms": 9.0,
                    "attempted_provider": "ollama",
                    "attempted_model": "gemma4:26b",
                },
            )()

        monkeypatch.setattr(assistant_api, "generate_simulation_summary", fake_generate)
        monkeypatch.setattr(assistant_api, "uuid4", lambda: trace_id)
        monkeypatch.setattr(
            assistant_api.logger,
            "info",
            lambda message, *args: logged.append((message, args)),
        )

        response = await assistant_api.summarize_simulation(sim_id, db=db, user=user)

        assert response.generation_mode == "llm"
        assert response.generation_provider == "ollama"
        assert response.generation_model == "gemma4:26b"
        assert response.trace_id == trace_id
        assert logged
        assert "llm_success=%s" in logged[0][0]
        assert "fallback_used=%s" in logged[0][0]
        assert logged[0][1][3] == "true"
        assert logged[0][1][4] == "false"

    @pytest.mark.asyncio
    async def test_summarize_simulation_raises_404_for_missing_simulation(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        sim_id = uuid4()
        trace_id = uuid4()
        user = User(
            id=uuid4(),
            email="user@example.com",
            is_active=True,
            is_verified=True,
            role=UserRole.USER,
        )
        db = _FakeAsyncSession(None)
        logged: list[tuple[str, tuple[object, ...]]] = []

        monkeypatch.setattr(assistant_api, "uuid4", lambda: trace_id)
        monkeypatch.setattr(
            assistant_api.logger,
            "info",
            lambda message, *args: logged.append((message, args)),
        )

        with pytest.raises(assistant_api.HTTPException) as exc_info:
            await assistant_api.summarize_simulation(sim_id, db=db, user=user)

        assert exc_info.value.status_code == 404
        assert exc_info.value.detail == "Simulation not found"
        assert logged
        assert "status=not_found" in logged[0][0]
        assert "llm_success=false" in logged[0][0]
        assert "fallback_used=false" in logged[0][0]
        assert logged[0][1][0] == trace_id
        assert logged[0][1][1] == sim_id
