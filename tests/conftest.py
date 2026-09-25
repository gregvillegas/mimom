import os
from pathlib import Path

import django
from django.conf import settings

BASE_DIR = Path(__file__).resolve().parent.parent

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.development")


def pytest_configure():
    if not settings.configured:
        django.setup()


import pytest  # noqa: E402


@pytest.fixture
def advance_meeting():
    """Walk a meeting to a target status via valid transitions with role checks skipped.

    Works even when the source status would otherwise create a non-adjacent invalid
    direct transition (e.g. DRAFT -> IN_PROGRESS) by composing the valid DAG path.
    """

    from apps.meetings.services import VALID_TRANSITIONS, transition_meeting

    def _walk(meeting, target, *, by_user, reason: str = ""):
        start = meeting.status
        if start == target:
            return
        # BFS shortest path over VALID_TRANSITIONS adjacency
        from collections import deque

        seen = {start: [start]}
        q = deque([start])
        path = None
        while q:
            node = q.popleft()
            if node == target:
                path = seen[node]
                break
            for nb in sorted(VALID_TRANSITIONS.get(node, set())):
                if nb in seen:
                    continue
                seen[nb] = seen[node] + [nb]
                q.append(nb)
        if path is None:
            raise ValueError(f"No valid path from {start} to {target}.")
        for step in path[1:]:
            transition_meeting(
                meeting,
                step,
                by_user=by_user,
                reason=reason or f"advance to {step}",
                skip_role_check=True,
            )
            meeting.refresh_from_db()

    return _walk
