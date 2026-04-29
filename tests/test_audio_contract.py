"""Tests for audio contract schemas and emotion mapping."""

import pytest
from pydantic import ValidationError

from ace_music.schemas.audio_contract import (
    AudioSceneContract,
    AudioSegmentCue,
    TTSSegment,
)
from ace_music.tools.emotion_mapper import map_scene_contract


def test_audio_scene_contract_defaults():
    contract = AudioSceneContract(
        scene_id="scene_001",
        duration_seconds=30.0,
        mood="tense",
    )

    assert contract.scene_id == "scene_001"
    assert contract.intensity == 0.5
    assert contract.layers.tts_present is True
    assert contract.qa_targets.min_composition_success_rate == 0.98


def test_audio_scene_contract_validates_arousal_range():
    with pytest.raises(ValidationError):
        AudioSceneContract(
            scene_id="bad_scene",
            duration_seconds=30.0,
            mood="tense",
            arousal=1.2,
        )


def test_audio_scene_contract_serialization_roundtrip_preserves_nested_values():
    contract = AudioSceneContract(
        scene_id="scene_roundtrip",
        duration_seconds=42.0,
        mood="hopeful",
        intensity=0.7,
        scene_description="Sunlight breaks through after a storm.",
        role_theme="hero",
        segments=[
            AudioSegmentCue(
                segment_id="intro",
                start_seconds=0.0,
                end_seconds=12.0,
                mood="calm",
                intensity=0.3,
            ),
            AudioSegmentCue(
                segment_id="lift",
                start_seconds=12.0,
                end_seconds=42.0,
                mood="hopeful",
                intensity=0.8,
            ),
        ],
    )

    payload = contract.model_dump(mode="json")
    restored = AudioSceneContract.model_validate(payload)

    assert restored.role_theme == "hero"
    assert restored.layers.tts_present is True
    assert restored.transition.crossfade_seconds == 1.5
    assert restored.segments[0].segment_id == "intro"
    assert restored.segments[1].intensity == 0.8


def test_mapper_turns_high_arousal_into_fast_tempo_and_ducking():
    contract = AudioSceneContract(
        scene_id="chase",
        duration_seconds=45.0,
        mood="urgent",
        intensity=0.9,
        arousal=0.95,
        valence=-0.3,
        shot_count=18,
        dialogue_density=0.8,
    )

    mapped = map_scene_contract(contract)

    assert mapped.tempo_preference == "fast"
    assert mapped.guidance_scale >= 16.0
    assert "tense" in mapped.style_tags
    assert mapped.mix.bgm_gain_db <= -12.0
    assert mapped.mix.ducking_db >= 8.0


def test_audio_scene_contract_serializes_segments():
    contract = AudioSceneContract(
        scene_id="scene_segments",
        duration_seconds=25.0,
        mood="melancholic",
        segments=[
            AudioSegmentCue(
                segment_id="seg_a",
                start_seconds=0.0,
                end_seconds=10.0,
                mood="melancholic",
                intensity=0.4,
            )
        ],
    )

    payload = contract.model_dump(mode="json")
    restored = AudioSceneContract.model_validate(payload)

    assert restored.segments[0].segment_id == "seg_a"
    assert restored.segments[0].end_seconds == 10.0


def test_audio_segment_cue_rejects_invalid_range():
    with pytest.raises(ValidationError):
        AudioSegmentCue(
            segment_id="bad_segment",
            start_seconds=5.0,
            end_seconds=5.0,
        )


def test_tts_segment_rejects_invalid_range():
    with pytest.raises(ValidationError):
        TTSSegment(
            start_seconds=2.0,
            end_seconds=2.0,
        )


def test_audio_scene_contract_rejects_overlapping_segments():
    with pytest.raises(ValidationError, match="must not overlap"):
        AudioSceneContract(
            scene_id="scene_overlap",
            duration_seconds=30.0,
            mood="tense",
            segments=[
                AudioSegmentCue(
                    segment_id="seg_a",
                    start_seconds=0.0,
                    end_seconds=12.0,
                ),
                AudioSegmentCue(
                    segment_id="seg_b",
                    start_seconds=10.0,
                    end_seconds=20.0,
                ),
            ],
        )


def test_audio_scene_contract_rejects_overlapping_tts_segments():
    with pytest.raises(ValidationError, match="tts_segments must not overlap"):
        AudioSceneContract(
            scene_id="scene_tts_overlap",
            duration_seconds=10.0,
            mood="tense",
            tts_segments=[
                TTSSegment(start_seconds=0.0, end_seconds=2.0),
                TTSSegment(start_seconds=1.5, end_seconds=3.0),
            ],
        )


def test_audio_scene_contract_rejects_unordered_tts_segments():
    with pytest.raises(ValidationError, match="tts_segments must be ordered"):
        AudioSceneContract(
            scene_id="scene_tts_order",
            duration_seconds=10.0,
            mood="tense",
            tts_segments=[
                TTSSegment(start_seconds=3.0, end_seconds=4.0),
                TTSSegment(start_seconds=1.0, end_seconds=2.0),
            ],
        )


def test_audio_scene_contract_rejects_tts_segment_beyond_scene_duration():
    with pytest.raises(ValidationError, match="tts_segments end_seconds must be <="):
        AudioSceneContract(
            scene_id="scene_tts_overflow",
            duration_seconds=10.0,
            mood="tense",
            tts_segments=[
                TTSSegment(start_seconds=9.0, end_seconds=10.5),
            ],
        )


def test_audio_scene_contract_rejects_segment_beyond_scene_duration():
    with pytest.raises(ValidationError, match="must be <= duration_seconds"):
        AudioSceneContract(
            scene_id="scene_overflow",
            duration_seconds=15.0,
            mood="calm",
            segments=[
                AudioSegmentCue(
                    segment_id="seg_a",
                    start_seconds=0.0,
                    end_seconds=16.0,
                )
            ],
        )


def test_mapper_normalizes_mood_before_style_tag_lookup():
    contract = AudioSceneContract(
        scene_id="scene_normalized_mood",
        duration_seconds=20.0,
        mood=" urgent ",
        intensity=0.8,
        arousal=0.9,
    )

    mapped = map_scene_contract(contract)

    assert "urgent" in mapped.style_tags
    assert "tense" in mapped.style_tags


def test_mapper_keeps_no_tts_sidechain_disabled_without_extra_ducking():
    contract = AudioSceneContract(
        scene_id="scene_no_tts",
        duration_seconds=35.0,
        mood="tense",
        dialogue_density=0.95,
        layers={"tts_present": False},
    )

    mapped = map_scene_contract(contract)

    assert mapped.mix.sidechain_source == "none"
    assert mapped.mix.ducking_db == contract.mix.ducking_db
