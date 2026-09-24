import pytest
from django.contrib.auth import get_user_model

User = get_user_model()


@pytest.mark.django_db
def test_custom_user_create():
    user = User.objects.create_user(
        username="jdoe",
        email="jdoe@example.com",
        password="pw-1234!",
        first_name="John",
        last_name="Doe",
    )
    assert user.pk is not None
    assert user.username == "jdoe"
    assert user.email == "jdoe@example.com"
    assert str(user) == "John Doe"
    assert user.get_display_name() == "John Doe"
    assert user.get_initials() == "JD"


@pytest.mark.django_db
def test_custom_user_display_name_fallback():
    user = User.objects.create_user(
        username="qa",
        email="qa@example.com",
        password="pw-1234!",
    )
    assert user.get_display_name() == "qa"
    assert user.get_initials() == "QA"


@pytest.mark.django_db
def test_custom_user_initials_override():
    user = User.objects.create_user(
        username="mgmt",
        email="mgmt@example.com",
        password="pw-1234!",
        initials="MGT",
    )
    assert user.get_initials() == "MGT"


@pytest.mark.django_db
def test_superuser_create():
    superuser = User.objects.create_superuser(
        username="admin",
        email="admin@example.com",
        password="pw-1234!",
    )
    assert superuser.is_staff is True
    assert superuser.is_superuser is True
    assert superuser.is_active is True


@pytest.mark.django_db
def test_custom_user_username_required():
    with pytest.raises(ValueError):
        User.objects.create_user(username="", email="a@b.com", password="pw")
