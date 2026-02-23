import uuid

from app.features.user.models import ApiToken, User, UserRole


class TestUser:
    def test_user_repr(self):
        """Test the __repr__ method of the User model."""
        user_id = uuid.uuid4()
        user = User(id=user_id, email="test@example.com", role=UserRole.ADMIN)
        expected_repr = (
            f"<User id={user_id} email='test@example.com' role=UserRole.ADMIN>"
        )

        assert repr(user) == expected_repr


class TestApiToken:
    def test_api_token_repr(self):
        """Test the __repr__ method of the ApiToken model."""
        token_id = uuid.uuid4()
        user_id = uuid.uuid4()
        api_token = ApiToken(
            id=token_id,
            name="test-token",
            token_hash="abc123",
            user_id=user_id,
        )
        expected_repr = f"<ApiToken id={token_id} name='test-token' user_id={user_id}>"

        assert repr(api_token) == expected_repr
