"""Cross-meeting speaker matching using embedding similarity.

Compares speaker embeddings from diarization against stored embeddings in the
database to identify returning speakers across meetings.
"""

from __future__ import annotations

import math
import struct
from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from db.database import DatabaseManager


@dataclass
class SpeakerMatch:
    """A match between a diarization label and a known speaker.

    Attributes:
        speaker_label: The diarization label (e.g. "SPEAKER_00").
        matched_name: The identified speaker name, or None if unknown.
        confidence: Match confidence between 0.0 and 1.0.
    """

    speaker_label: str
    matched_name: str | None
    confidence: float


class SpeakerIdentifier:
    """Matches speaker embeddings against a stored library of known speakers.

    Uses cosine similarity to compare diarization-produced embeddings with
    stored embeddings from previous meetings.

    Usage:
        identifier = SpeakerIdentifier(db)
        matches = identifier.identify(embeddings={"SPEAKER_00": [...], "SPEAKER_01": [...]})
    """

    def __init__(
        self,
        db: DatabaseManager | None = None,
        similarity_threshold: float = 0.75,
    ) -> None:
        self.db = db
        self.similarity_threshold = similarity_threshold

    def identify(
        self,
        embeddings: dict[str, list[float]],
        known_embeddings: dict[str, list[float]] | None = None,
    ) -> list[SpeakerMatch]:
        """Match speaker embeddings against known speakers.

        Args:
            embeddings: Mapping of diarization labels to embedding vectors.
            known_embeddings: Mapping of speaker names to stored embedding vectors.

        Returns:
            List of speaker matches with confidence scores.
        """
        if known_embeddings is None:
            known_embeddings = {}

        matches: list[SpeakerMatch] = []
        for label, embedding in embeddings.items():
            best_name: str | None = None
            best_similarity: float = 0.0

            for name, known_vec in known_embeddings.items():
                sim = self.cosine_similarity(embedding, known_vec)
                if sim > best_similarity:
                    best_similarity = sim
                    best_name = name

            if best_name is not None and best_similarity >= self.similarity_threshold:
                matches.append(
                    SpeakerMatch(
                        speaker_label=label,
                        matched_name=best_name,
                        confidence=best_similarity,
                    )
                )
            else:
                matches.append(
                    SpeakerMatch(
                        speaker_label=label,
                        matched_name=None,
                        confidence=best_similarity,
                    )
                )

        return matches

    def identify_from_db(self, embeddings: dict[str, list[float]]) -> list[SpeakerMatch]:
        """Load known speakers from the database and identify input embeddings.

        Args:
            embeddings: Mapping of diarization labels to embedding vectors.

        Returns:
            List of speaker matches with confidence scores.

        Raises:
            RuntimeError: If no database connection is configured.
        """
        if self.db is None:
            raise RuntimeError("Database not configured. Pass a db to SpeakerIdentifier.")

        speakers = self.db.get_all_speakers()
        known_embeddings: dict[str, list[float]] = {}
        for speaker in speakers:
            stored_blob = speaker["embedding"]
            if stored_blob is None:
                continue
            known_embeddings[speaker["name"]] = self.deserialize_embedding(stored_blob)

        return self.identify(embeddings, known_embeddings=known_embeddings)

    def update_speaker_embedding(self, speaker_id: int, new_embedding: list[float]) -> None:
        """Update a speaker's stored embedding using a running average.

        Computes: updated = (old * count + new) / (count + 1)

        Args:
            speaker_id: The database ID of the speaker to update.
            new_embedding: The new embedding vector from the latest meeting.

        Raises:
            RuntimeError: If no database connection is configured.
        """
        if self.db is None:
            raise RuntimeError("Database not configured. Pass a db to SpeakerIdentifier.")

        speaker = self.db.get_speaker(speaker_id)
        if speaker is None:
            return
        old_blob = speaker["embedding"]
        old_count: int = speaker["embedding_count"]

        if old_blob is None or old_count == 0:
            # First embedding -- store as-is
            updated = new_embedding
            new_count = 1
        else:
            old_embedding = self.deserialize_embedding(old_blob)
            new_count = old_count + 1
            updated = [
                (old_val * old_count + new_val) / new_count
                for old_val, new_val in zip(old_embedding, new_embedding)
            ]

        self.db.update_speaker_embedding(speaker_id, self.serialize_embedding(updated), new_count)

    @staticmethod
    def cosine_similarity(vec_a: list[float], vec_b: list[float]) -> float:
        """Compute cosine similarity between two vectors.

        Args:
            vec_a: First embedding vector.
            vec_b: Second embedding vector.

        Returns:
            Similarity score between -1.0 and 1.0.
            Returns 0.0 if either vector has zero magnitude.
        """
        dot = sum(a * b for a, b in zip(vec_a, vec_b))
        norm_a = math.sqrt(sum(a * a for a in vec_a))
        norm_b = math.sqrt(sum(b * b for b in vec_b))

        if norm_a == 0.0 or norm_b == 0.0:
            return 0.0

        return dot / (norm_a * norm_b)

    @staticmethod
    def serialize_embedding(embedding: list[float]) -> bytes:
        """Pack a float list to bytes for database storage.

        Args:
            embedding: List of float values (typically 256-dim).

        Returns:
            Bytes packed as float32 values using struct.
        """
        return struct.pack(f"{len(embedding)}f", *embedding)

    @staticmethod
    def deserialize_embedding(data: bytes) -> list[float]:
        """Unpack bytes back to a float list.

        Args:
            data: Bytes containing struct-packed float32 values.

        Returns:
            List of float values.
        """
        if len(data) == 0:
            return []
        count = len(data) // 4
        return list(struct.unpack(f"{count}f", data))
