"""Tests for the speaker identification module."""

from __future__ import annotations

from speaker_id.identifier import SpeakerIdentifier


class TestSpeakerIdentifier:
    """Tests for SpeakerIdentifier matching logic."""

    def test_identify_returns_matches_for_each_speaker(self) -> None:
        """Verify that identify returns one match per input embedding."""
        identifier = SpeakerIdentifier()
        embeddings = {
            "SPEAKER_00": [0.1, 0.2, 0.3],
            "SPEAKER_01": [0.4, 0.5, 0.6],
        }
        matches = identifier.identify(embeddings)
        assert len(matches) == 2
        labels = {m.speaker_label for m in matches}
        assert labels == {"SPEAKER_00", "SPEAKER_01"}

    def test_identify_with_no_known_speakers_returns_unmatched(self) -> None:
        """Verify that without known speakers, all matches have None name."""
        identifier = SpeakerIdentifier()
        matches = identifier.identify({"SPEAKER_00": [0.1, 0.2]})
        assert all(m.matched_name is None for m in matches)

    def test_cosine_similarity_stub_returns_zero(self) -> None:
        """Verify that the stub cosine_similarity returns 0.0."""
        result = SpeakerIdentifier.cosine_similarity([1.0, 0.0], [0.0, 1.0])
        assert result == 0.0

    def test_custom_threshold(self) -> None:
        """Verify that the similarity threshold is configurable."""
        identifier = SpeakerIdentifier(similarity_threshold=0.9)
        assert identifier.similarity_threshold == 0.9
