"""Tests for UserStory model."""

from uuid import uuid4

from app.domain.enums import ArtifactStatus
from app.domain.user_story import UserStory


def test_user_story_creation():
    story = UserStory(
        id="US-001",
        project_id=uuid4(),
        as_a="registered user",
        i_want="reset my password",
        so_that="I can regain access to my account",
    )
    assert story.as_a == "registered user"
    assert story.i_want == "reset my password"
    assert story.so_that == "I can regain access to my account"
    assert story.status == ArtifactStatus.draft
