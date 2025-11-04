import uuid

from app.features.user.models import User, UserRole


class TestUser:
    def test_user_repr(self):
        """Test the __repr__ method of the User model."""
        user_id = uuid.uuid4()
        user = User(id=user_id, email="test@example.com", role=UserRole.ADMIN)
        expected_repr = (
            f"<User id={user_id} email='test@example.com' role=UserRole.ADMIN>"
        )

        assert repr(user) == expected_repr
