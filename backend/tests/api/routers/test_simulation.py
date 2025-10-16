from uuid import uuid4

import pytest
from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.api.routers.simulation import (
    create_simulation,
    get_simulation,
    list_simulations,
)
from app.db.machine import Machine
from app.db.simulation import Simulation
from app.schemas.simulation import SimulationCreate


class TestCreateSimulation:
    def test_create_simulation_success(self, client, db: Session):
        machine = db.query(Machine).first()
        assert machine is not None, "No machine found in the database"

        payload = {
            "name": "Test Simulation",
            "caseName": "test_case",
            "compset": "AQUAPLANET",
            "compsetAlias": "QPC4",
            "gridName": "f19_f19",
            "gridResolution": "1.9x2.5",
            "initializationType": "startup",
            "simulationType": "control",
            "status": "created",
            "machineId": str(machine.id),
            "simulationStartDate": "2023-01-01T00:00:00Z",
            "gitTag": "v1.0",
            "gitCommitHash": "abc123",
            "artifacts": [
                {
                    "kind": "output",
                    "uri": "http://example.com/artifact1",
                    "label": "artifact1",
                }
            ],
            "links": [
                {
                    "kind": "diagnostic",
                    "url": "http://example.com/link1",
                    "label": "link1",
                }
            ],
        }

        # Test function directly
        simulation_create = SimulationCreate(**payload)  # type: ignore
        simulation = create_simulation(simulation_create, db)
        assert simulation.name == payload["name"]
        assert len(simulation.artifacts) == 1
        assert len(simulation.links) == 1

        # Test API endpoint
        payload2 = payload.copy()
        payload2.update({"name": "Test Simulation 2", "caseName": "test_case_2"})

        r = client.post("/simulations", json=payload2)
        assert r.status_code == 201

        data = r.json()
        assert data["name"] == payload2["name"]
        assert len(data["artifacts"]) == 1
        assert len(data["links"]) == 1


class TestListSimulations:
    def test_list_simulations_empty(self, client, db: Session):
        # Test API endpoint
        r = client.get("/simulations")
        assert r.status_code == 200
        assert r.json() == []

        # Test function directly
        simulations = list_simulations(db)
        assert simulations == []

    def test_list_simulations_with_data(self, db: Session, client):
        machine = db.query(Machine).first()
        assert machine is not None, "No machine found in the database"

        sim = Simulation(
            name="Test Simulation",
            case_name="test_case",
            compset="AQUAPLANET",
            compset_alias="QPC4",
            grid_name="f19_f19",
            grid_resolution="1.9x2.5",
            initialization_type="startup",
            simulation_type="control",
            status="created",
            machine_id=machine.id,
            simulation_start_date="2023-01-01T00:00:00Z",
            git_tag="v1.0",
            git_commit_hash="abc123",
        )
        db.add(sim)
        db.commit()
        db.refresh(sim)

        # Test API endpoint
        r = client.get("/simulations")
        assert r.status_code == 200

        data = r.json()
        assert len(data) == 1
        assert data[0]["name"] == sim.name

        # Test function directly
        simulations = list_simulations(db)
        assert len(simulations) == 1
        assert simulations[0].name == sim.name


class TestGetSimulation:
    def test_get_simulation_success(self, db: Session, client):
        machine = db.query(Machine).first()
        assert machine is not None, "No machine found in the database"

        sim = Simulation(
            name="Test Simulation",
            case_name="test_case",
            compset="AQUAPLANET",
            compset_alias="QPC4",
            grid_name="f19_f19",
            grid_resolution="1.9x2.5",
            initialization_type="startup",
            simulation_type="control",
            status="created",
            machine_id=machine.id,
            simulation_start_date="2023-01-01T00:00:00Z",
            git_tag="v1.0",
            git_commit_hash="abc123",
        )
        db.add(sim)
        db.commit()
        db.refresh(sim)

        # Test function directly
        simulation = get_simulation(sim.id, db)
        assert simulation.name == sim.name

        # Test API endpoint
        r = client.get(f"/simulations/{sim.id}")
        assert r.status_code == 200
        assert r.json()["name"] == sim.name

    def test_get_simulation_not_found(self, client, db: Session):
        # Test function directly
        with pytest.raises(HTTPException, match="Simulation not found"):
            get_simulation(uuid4(), db)

        # Test API endpoint
        r = client.get(f"/simulations/{uuid4()}")
        assert r.status_code == 404
        assert r.json() == {"detail": "Simulation not found"}
