"""Tests for the speaker identification module."""

from __future__ import annotations

import random
import struct
from unittest.mock import MagicMock

import pytest

from speaker_id.identifier import SpeakerIdentifier, SpeakerMatch


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


class TestCosineSimilarity:
    """Tests for cosine_similarity computation."""

    def test_identical_vectors_returns_one(self) -> None:
        """Cosine similarity of a vector with itself should be 1.0."""
        vec = [1.0, 2.0, 3.0]
        result = SpeakerIdentifier.cosine_similarity(vec, vec)
        assert result == pytest.approx(1.0)

    def test_orthogonal_vectors_returns_zero(self) -> None:
        """Cosine similarity of perpendicular vectors should be 0.0."""
        vec_a = [1.0, 0.0]
        vec_b = [0.0, 1.0]
        result = SpeakerIdentifier.cosine_similarity(vec_a, vec_b)
        assert result == pytest.approx(0.0)

    def test_opposite_vectors_returns_negative_one(self) -> None:
        """Cosine similarity of opposite vectors should be -1.0."""
        vec_a = [1.0, 2.0, 3.0]
        vec_b = [-1.0, -2.0, -3.0]
        result = SpeakerIdentifier.cosine_similarity(vec_a, vec_b)
        assert result == pytest.approx(-1.0)

    def test_zero_vector_returns_zero(self) -> None:
        """Cosine similarity involving a zero vector should return 0.0."""
        zero = [0.0, 0.0, 0.0]
        other = [1.0, 2.0, 3.0]
        assert SpeakerIdentifier.cosine_similarity(zero, other) == 0.0
        assert SpeakerIdentifier.cosine_similarity(other, zero) == 0.0
        assert SpeakerIdentifier.cosine_similarity(zero, zero) == 0.0

    def test_256_dim_vectors_in_valid_range(self) -> None:
        """Cosine similarity of random 256-dim vectors falls in [-1, 1]."""
        random.seed(42)
        vec_a = [random.gauss(0, 1) for _ in range(256)]
        vec_b = [random.gauss(0, 1) for _ in range(256)]
        result = SpeakerIdentifier.cosine_similarity(vec_a, vec_b)
        assert -1.0 <= result <= 1.0


class TestIdentify:
    """Tests for the identify method matching logic."""

    def test_matches_known_speaker_above_threshold(self) -> None:
        """Identify should match a speaker when similarity exceeds threshold."""
        identifier = SpeakerIdentifier(similarity_threshold=0.75)
        # Use identical vectors to guarantee a match
        embedding = [1.0, 0.0, 0.0]
        embeddings = {"SPEAKER_00": embedding}
        known = {"Alice": embedding}
        matches = identifier.identify(embeddings, known_embeddings=known)
        assert len(matches) == 1
        assert matches[0].speaker_label == "SPEAKER_00"
        assert matches[0].matched_name == "Alice"
        assert matches[0].confidence == pytest.approx(1.0)

    def test_returns_none_for_speaker_below_threshold(self) -> None:
        """Identify should return None matched_name when below threshold."""
        identifier = SpeakerIdentifier(similarity_threshold=0.99)
        embeddings = {"SPEAKER_00": [1.0, 0.5, 0.0]}
        known = {"Alice": [0.5, 1.0, 0.0]}
        matches = identifier.identify(embeddings, known_embeddings=known)
        assert len(matches) == 1
        assert matches[0].matched_name is None
        # confidence should still report the best similarity found
        assert matches[0].confidence > 0.0

    def test_picks_best_match_among_multiple_known_speakers(self) -> None:
        """Identify should pick the closest known speaker when multiple exist."""
        identifier = SpeakerIdentifier(similarity_threshold=0.5)
        target = [1.0, 0.0, 0.0]
        embeddings = {"SPEAKER_00": target}
        known = {
            "Alice": [1.0, 0.0, 0.0],  # identical -> similarity 1.0
            "Bob": [0.0, 1.0, 0.0],  # orthogonal -> similarity 0.0
        }
        matches = identifier.identify(embeddings, known_embeddings=known)
        assert matches[0].matched_name == "Alice"
        assert matches[0].confidence == pytest.approx(1.0)

    def test_returns_unmatched_for_all_when_no_known_speakers(self) -> None:
        """All matches should be unmatched when known_embeddings is empty."""
        identifier = SpeakerIdentifier()
        embeddings = {
            "SPEAKER_00": [1.0, 0.0],
            "SPEAKER_01": [0.0, 1.0],
        }
        matches = identifier.identify(embeddings, known_embeddings={})
        assert len(matches) == 2
        assert all(m.matched_name is None for m in matches)
        assert all(m.confidence == 0.0 for m in matches)

    def test_handles_empty_embeddings_dict(self) -> None:
        """Identify should return empty list when no input embeddings given."""
        identifier = SpeakerIdentifier()
        matches = identifier.identify({}, known_embeddings={"Alice": [1.0]})
        assert matches == []


class TestSerialization:
    """Tests for embedding serialize/deserialize helpers."""

    def test_serialize_deserialize_round_trip(self) -> None:
        """Serializing then deserializing should return the original embedding."""
        original = [0.1, 0.2, 0.3, -0.5, 1.0]
        serialized = SpeakerIdentifier.serialize_embedding(original)
        restored = SpeakerIdentifier.deserialize_embedding(serialized)
        for orig, rest in zip(original, restored):
            assert rest == pytest.approx(orig, abs=1e-6)

    def test_serialize_produces_correct_byte_length(self) -> None:
        """Each float32 should produce exactly 4 bytes."""
        embedding = [1.0, 2.0, 3.0]
        data = SpeakerIdentifier.serialize_embedding(embedding)
        assert len(data) == 4 * len(embedding)

    def test_deserialize_empty_bytes_returns_empty_list(self) -> None:
        """Deserializing empty bytes should return an empty list."""
        result = SpeakerIdentifier.deserialize_embedding(b"")
        assert result == []

    def test_serialize_256_dim_round_trip(self) -> None:
        """Round-trip a full 256-dimensional embedding vector."""
        random.seed(99)
        original = [random.gauss(0, 1) for _ in range(256)]
        serialized = SpeakerIdentifier.serialize_embedding(original)
        assert len(serialized) == 256 * 4
        restored = SpeakerIdentifier.deserialize_embedding(serialized)
        assert len(restored) == 256
        for orig, rest in zip(original, restored):
            assert rest == pytest.approx(orig, abs=1e-6)


class TestIdentifyFromDb:
    """Tests for identify_from_db with mocked database."""

    def test_loads_speakers_and_identifies(self) -> None:
        """identify_from_db should load known speakers from db and match."""
        mock_db = MagicMock()
        embedding = [1.0, 0.0, 0.0]
        packed = struct.pack(f"{len(embedding)}f", *embedding)

        # Mock a speaker row returned by get_all_speakers
        speaker_row = {"id": 1, "name": "Alice", "embedding": packed, "embedding_count": 3}
        mock_db.get_all_speakers.return_value = [speaker_row]

        identifier = SpeakerIdentifier(db=mock_db, similarity_threshold=0.75)
        matches = identifier.identify_from_db({"SPEAKER_00": embedding})

        assert len(matches) == 1
        assert matches[0].matched_name == "Alice"
        assert matches[0].confidence == pytest.approx(1.0)
        mock_db.get_all_speakers.assert_called_once()

    def test_raises_runtime_error_without_db(self) -> None:
        """identify_from_db should raise RuntimeError when db is None."""
        identifier = SpeakerIdentifier()
        with pytest.raises(RuntimeError, match="[Dd]atabase"):
            identifier.identify_from_db({"SPEAKER_00": [1.0, 0.0]})

    def test_skips_speakers_without_embeddings(self) -> None:
        """identify_from_db should skip speakers with no stored embedding."""
        mock_db = MagicMock()
        speaker_no_embedding = {"id": 1, "name": "Bob", "embedding": None, "embedding_count": 0}
        mock_db.get_all_speakers.return_value = [speaker_no_embedding]

        identifier = SpeakerIdentifier(db=mock_db)
        matches = identifier.identify_from_db({"SPEAKER_00": [1.0, 0.0, 0.0]})

        assert len(matches) == 1
        assert matches[0].matched_name is None


class TestUpdateSpeakerEmbedding:
    """Tests for update_speaker_embedding running average."""

    def test_computes_running_average(self) -> None:
        """update_speaker_embedding should compute a running average of embeddings."""
        mock_db = MagicMock()
        old_embedding = [1.0, 0.0, 0.0]
        packed_old = struct.pack(f"{len(old_embedding)}f", *old_embedding)
        speaker_row = {
            "id": 1,
            "name": "Alice",
            "embedding": packed_old,
            "embedding_count": 2,
        }
        mock_db.get_speaker.return_value = speaker_row

        identifier = SpeakerIdentifier(db=mock_db)
        new_embedding = [0.0, 3.0, 0.0]
        identifier.update_speaker_embedding(1, new_embedding)

        # Running average: (old * count + new) / (count + 1)
        # = ([1.0, 0.0, 0.0] * 2 + [0.0, 3.0, 0.0]) / 3
        # = [2.0, 3.0, 0.0] / 3
        # = [2/3, 1.0, 0.0]
        mock_db.update_speaker_embedding.assert_called_once()
        call_args = mock_db.update_speaker_embedding.call_args
        assert call_args[0][0] == 1  # speaker_id
        stored_bytes = call_args[0][1]
        stored_embedding = SpeakerIdentifier.deserialize_embedding(stored_bytes)
        assert stored_embedding[0] == pytest.approx(2.0 / 3.0, abs=1e-5)
        assert stored_embedding[1] == pytest.approx(1.0, abs=1e-5)
        assert stored_embedding[2] == pytest.approx(0.0, abs=1e-5)
        assert call_args[0][2] == 3  # new count

    def test_handles_first_embedding(self) -> None:
        """update_speaker_embedding should store the first embedding as-is."""
        mock_db = MagicMock()
        speaker_row = {
            "id": 1,
            "name": "Alice",
            "embedding": None,
            "embedding_count": 0,
        }
        mock_db.get_speaker.return_value = speaker_row

        identifier = SpeakerIdentifier(db=mock_db)
        new_embedding = [0.5, 0.5, 0.5]
        identifier.update_speaker_embedding(1, new_embedding)

        call_args = mock_db.update_speaker_embedding.call_args
        stored_bytes = call_args[0][1]
        stored_embedding = SpeakerIdentifier.deserialize_embedding(stored_bytes)
        for i in range(3):
            assert stored_embedding[i] == pytest.approx(0.5, abs=1e-6)
        assert call_args[0][2] == 1  # count = 1

    def test_raises_runtime_error_without_db(self) -> None:
        """update_speaker_embedding should raise RuntimeError when db is None."""
        identifier = SpeakerIdentifier()
        with pytest.raises(RuntimeError, match="[Dd]atabase"):
            identifier.update_speaker_embedding(1, [1.0, 0.0])


class TestSpeakerMatchDefaults:
    """Tests for SpeakerMatch dataclass."""

    def test_speaker_match_stores_fields(self) -> None:
        """SpeakerMatch should store label, name, and confidence."""
        match = SpeakerMatch(
            speaker_label="SPEAKER_00",
            matched_name="Alice",
            confidence=0.85,
        )
        assert match.speaker_label == "SPEAKER_00"
        assert match.matched_name == "Alice"
        assert match.confidence == 0.85

    def test_speaker_match_none_name(self) -> None:
        """SpeakerMatch should accept None as matched_name for unknown speakers."""
        match = SpeakerMatch(
            speaker_label="SPEAKER_01",
            matched_name=None,
            confidence=0.3,
        )
        assert match.matched_name is None


class TestSpeakerIdentifierInit:
    """Tests for SpeakerIdentifier constructor."""

    def test_default_init_no_db(self) -> None:
        """SpeakerIdentifier should default to db=None."""
        identifier = SpeakerIdentifier()
        assert identifier.db is None

    def test_init_with_db(self) -> None:
        """SpeakerIdentifier should accept a db parameter."""
        mock_db = MagicMock()
        identifier = SpeakerIdentifier(db=mock_db)
        assert identifier.db is mock_db

    def test_default_threshold(self) -> None:
        """SpeakerIdentifier should default to similarity_threshold=0.75."""
        identifier = SpeakerIdentifier()
        assert identifier.similarity_threshold == 0.75
