import pytest
from django.contrib.auth import get_user_model
from django.test import Client
from django.urls import reverse

User = get_user_model()


@pytest.mark.django_db
def test_health_check_anonymous():
    client = Client()
    url = reverse("health_check")
    response = client.get(url)
    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "ok"
    assert payload["database"] == "ok"
    assert "timestamp" in payload


@pytest.mark.django_db
def test_health_check_root_alias():
    client = Client()
    response = client.get("/health/")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


@pytest.mark.django_db
def test_home_requires_auth_redirect():
    client = Client()
    url = reverse("home")
    response = client.get(url, follow=False)
    assert response.status_code == 302
    assert "/login/" in response.url


@pytest.mark.django_db
def test_home_authenticated(user):
    client = Client()
    client.force_login(user)
    url = reverse("home")
    response = client.get(url)
    assert response.status_code == 200
    assert "Dashboard" in response.content.decode("utf-8")


@pytest.mark.django_db
def test_login_page_anonymous():
    client = Client()
    response = client.get(reverse("login"))
    assert response.status_code == 200
    content = response.content.decode("utf-8")
    assert "id_username" in content
    assert "id_password" in content
    assert "Sign in" in content


@pytest.fixture
def user(db):
    return User.objects.create_user(
        username="phase1user",
        email="phase1user@example.com",
        password="not-a-real-pw-123",
        first_name="Test",
        last_name="User",
    )
