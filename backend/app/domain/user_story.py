"""ENG-004 UserStory model."""

from typing import ClassVar

from .base import Artifact
from .enums import ArtifactKind, ArtifactStatus


class UserStory(Artifact):
    """A user story in As / I want / So that format."""

    ARTIFACT_KIND: ClassVar[ArtifactKind] = ArtifactKind.user_story

    as_a: str
    i_want: str
    so_that: str
    status: ArtifactStatus = ArtifactStatus.draft
