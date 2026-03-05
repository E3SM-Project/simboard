from app.features.simulation.models import Simulation


class TestSimulationModel:
    def test_config_delta_fields_are_valid(self):
        model_columns = set(Simulation.__table__.columns.keys())
        assert Simulation.CONFIG_DELTA_FIELDS <= model_columns
