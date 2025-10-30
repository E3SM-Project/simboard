"""
Centralized model registry to ensure all SQLAlchemy models are imported once.
"""

from app.features.machine import models as machine_models  # noqa: F401
from app.features.simulation import models as simulation_models  # noqa: F401
from app.features.user import models as user_models  # noqa: F401
