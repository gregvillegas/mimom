from django.conf import settings


def test_settings_debug():
    assert settings.DEBUG is True or settings.DEBUG is False


def test_installed_apps_core():
    app_labels = {a.rsplit(".", 1)[-1] for a in settings.INSTALLED_APPS}
    for expected in [
        "core",
        "accounts",
        "meetings",
        "action_items",
        "sales_updates",
        "notifications",
        "audit",
    ]:
        assert expected in app_labels, f"Missing app: {expected}"


def test_auth_user_model():
    assert settings.AUTH_USER_MODEL == "accounts.User"


def test_static_and_media_roots():
    assert settings.STATIC_ROOT is not None
    assert settings.MEDIA_ROOT is not None


def test_login_urls():
    assert settings.LOGIN_URL == "login"
    assert settings.LOGIN_REDIRECT_URL == "home"
    assert settings.LOGOUT_REDIRECT_URL == "login"
