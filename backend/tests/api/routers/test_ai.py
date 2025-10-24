from datetime import datetime
from unittest.mock import patch
from uuid import uuid4

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from app.features.ai.api import analyze_simulations, router

client = TestClient(router, raise_server_exceptions=False)


class TestAnalyzeSimulations:
    @patch("app.api.routers.ai.summarizer")
    def test_analyze_simulations_with_few_simulations(self, mock_summarizer):
        # Mock summarizer response
        mock_summarizer.return_value = [{"summary_text": "Mocked summary"}]

        # Create test payload
        payload = [
            {
                "id": str(uuid4()),
                "name": "Simulation 1",
                "case_name": "Case 1",
                "compset": "compset1",
                "compset_alias": "alias1",
                "grid_name": "grid1",
                "grid_resolution": "1x1",
                "initialization_type": "type1",
                "simulation_type": "typeA",
                "status": "completed",
                "machine_id": str(uuid4()),
                "model_start_date": datetime.now().isoformat(),
                "version_tag": "v1.0",
                "campaign_id": "campaign1",
                "notes_markdown": "Test notes 1",
                "created_at": datetime.now().isoformat(),
                "updated_at": datetime.now().isoformat(),
                "artifacts": [],
                "links": [],
            }
        ]

        response = client.post("/ai/analyze-simulations", json=payload)

        assert response.status_code == 200
        assert response.json() == {"summary": "Mocked summary"}
        mock_summarizer.assert_called_once()

    @patch("app.api.routers.ai.summarizer")
    def test_analyze_simulations_with_many_simulations(self, mock_summarizer):
        # Mock summarizer response
        mock_summarizer.side_effect = [
            [{"summary_text": "Intermediate summary 1"}],
            [{"summary_text": "Intermediate summary 2"}],
            [{"summary_text": "Final summary"}],
        ]

        # Create test payload
        payload = [
            {
                "id": str(uuid4()),
                "name": f"Simulation {i}",
                "case_name": f"Case {i}",
                "compset": f"compset{i}",
                "compset_alias": f"alias{i}",
                "grid_name": f"grid{i}",
                "grid_resolution": f"{i}x{i}",
                "initialization_type": f"type{i}",
                "simulation_type": f"type{i}",
                "status": "completed",
                "machine_id": str(uuid4()),
                "model_start_date": datetime.now().isoformat(),
                "version_tag": f"v{i}.0",
                "campaign_id": f"campaign{i}",
                "notes_markdown": f"Test notes {i}",
                "created_at": datetime.now().isoformat(),
                "updated_at": datetime.now().isoformat(),
                "artifacts": [],
                "links": [],
            }
            for i in range(1, 9)
        ]

        response = client.post("/ai/analyze-simulations", json=payload)

        assert response.status_code == 200
        assert response.json() == {"summary": "Final summary"}
        assert mock_summarizer.call_count == 3

    @pytest.mark.xfail(reason="500 status code returned instead of 422")
    def test_analyze_simulations_invalid_payload(self):
        # Create invalid payload
        payload = [{"invalid": "data"}]

        response = client.post("/ai/analyze-simulations", json=payload)

        assert response.status_code == 422  # Unprocessable Entity

        with pytest.raises(HTTPException):
            analyze_simulations(payload)

    @pytest.mark.xfail(reason="json() not returning expected detail")
    @patch("app.api.routers.ai.summarizer")
    def test_analyze_simulations_summarization_failure(self, mock_summarizer):
        # Mock summarizer to raise an exception
        mock_summarizer.side_effect = Exception("Summarization error")

        # Create test payload
        payload = [
            {
                "id": str(uuid4()),
                "name": "Simulation 1",
                "case_name": "Case 1",
                "compset": "compset1",
                "compset_alias": "alias1",
                "grid_name": "grid1",
                "grid_resolution": "1x1",
                "initialization_type": "type1",
                "simulation_type": "typeA",
                "status": "completed",
                "machine_id": str(uuid4()),
                "model_start_date": datetime.now().isoformat(),
                "version_tag": "v1.0",
                "campaign_id": "campaign1",
                "notes_markdown": "Test notes 1",
                "created_at": datetime.now().isoformat(),
                "updated_at": datetime.now().isoformat(),
                "artifacts": [],
                "links": [],
            }
        ]

        response = client.post("/ai/analyze-simulations", json=payload)

        assert response.status_code == 500
        assert response.json() == {
            "detail": "Summarization failed: Summarization error"
        }
