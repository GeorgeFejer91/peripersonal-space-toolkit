"""Audio channel routing helpers for PPS playback.

The configurable renderer writes multichannel WAVs as:

- channel 0: binaural left ear
- channel 1: binaural right ear
- channel 2: vibrotactile cue

The locked Study 5 generator still writes legacy stereo WAVs as:

- channel 0: vibrotactile cue
- channel 1: mono/single-ear looming audio

These helpers keep the two layouts explicit and testable.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np


LEGACY_STEREO_CHANNELS = 2
BINAURAL_TACTILE_CHANNELS = 3
BINAURAL_TACTILE_PADDED_CHANNELS = 4
SPATIAL_AUDIO_CHANNELS = (0, 1)
LEGACY_AUDIO_CHANNELS = (0,)
LEGACY_TACTILE_CHANNEL = 1
SPATIAL_TACTILE_CHANNEL = 2


@dataclass(frozen=True)
class PreparedBlockAudio:
    data: np.ndarray
    layout: str
    channels: int
    source_channels: int
    audio_channels: tuple[int, ...]
    tactile_channel: int


def ensure_2d_float32(data: np.ndarray) -> np.ndarray:
    """Return audio as C-contiguous 2D float32 samples."""
    array = np.asarray(data, dtype=np.float32)
    if array.ndim == 1:
        array = array.reshape(-1, 1)
    if array.ndim != 2:
        raise ValueError(f"Expected mono or 2D audio samples, got shape {array.shape}.")
    return np.ascontiguousarray(array)


def tactile_output_channel_for_channels(channels: int) -> int:
    """Return the physical output channel index used for tactile cues."""
    return SPATIAL_TACTILE_CHANNEL if channels >= BINAURAL_TACTILE_CHANNELS else LEGACY_TACTILE_CHANNEL


def audio_output_channels_for_channels(channels: int) -> tuple[int, ...]:
    """Return physical output channel indices used for auditory playback."""
    return SPATIAL_AUDIO_CHANNELS if channels >= BINAURAL_TACTILE_CHANNELS else LEGACY_AUDIO_CHANNELS


def preferred_runtime_output_channels(max_output_channels: int) -> int:
    """Prefer a single 3-channel stream when the device supports it."""
    return BINAURAL_TACTILE_CHANNELS if max_output_channels >= BINAURAL_TACTILE_CHANNELS else LEGACY_STEREO_CHANNELS


def prepare_block_audio_for_output(data: np.ndarray, *, output_channels: int | None = None) -> PreparedBlockAudio:
    """Map a rendered/legacy block WAV into physical output-channel order.

    For 3+ channel rendered files, the first three source channels are already
    in physical order: left, right, tactile. For 2-channel legacy files, the
    original Study 5 mapping is preserved by swapping source right to output 0
    and source left to output 1.

    If ``output_channels`` is 4 or greater for rendered files, channel 3+ is
    padded with silence. This supports ASIO drivers that prefer even channel
    counts while keeping tactile on physical output channel 3.
    """
    array = ensure_2d_float32(data)
    source_channels = int(array.shape[1])
    if source_channels == 1:
        raise ValueError("Block WAVs must be legacy stereo or 3-channel binaural+tactile files.")

    if source_channels >= BINAURAL_TACTILE_CHANNELS:
        requested_channels = output_channels or BINAURAL_TACTILE_CHANNELS
        if requested_channels < BINAURAL_TACTILE_CHANNELS:
            raise ValueError("Binaural+tactile blocks require at least 3 output channels.")
        routed = np.zeros((array.shape[0], requested_channels), dtype=np.float32)
        routed[:, :BINAURAL_TACTILE_CHANNELS] = array[:, :BINAURAL_TACTILE_CHANNELS]
        return PreparedBlockAudio(
            data=np.ascontiguousarray(routed),
            layout="binaural_left_right_plus_tactile",
            channels=requested_channels,
            source_channels=source_channels,
            audio_channels=SPATIAL_AUDIO_CHANNELS,
            tactile_channel=SPATIAL_TACTILE_CHANNEL,
        )

    if output_channels is not None and output_channels != LEGACY_STEREO_CHANNELS:
        raise ValueError("Legacy stereo Study 5 blocks must be played through a 2-channel output stream.")
    routed = np.ascontiguousarray(array[:, [1, 0]])
    return PreparedBlockAudio(
        data=routed,
        layout="legacy_study5_stereo_audio_tactile",
        channels=LEGACY_STEREO_CHANNELS,
        source_channels=source_channels,
        audio_channels=LEGACY_AUDIO_CHANNELS,
        tactile_channel=LEGACY_TACTILE_CHANNEL,
    )


def apply_output_volumes(
    data: np.ndarray,
    audio_volume: float,
    tactile_volume: float,
    *,
    audio_channels: tuple[int, ...] | None = None,
    tactile_channel: int | None = None,
) -> np.ndarray:
    """Apply auditory and tactile gains to already-routed output data."""
    routed = ensure_2d_float32(data).copy()
    channels = routed.shape[1]
    audio_targets = audio_channels or audio_output_channels_for_channels(channels)
    tactile_target = tactile_output_channel_for_channels(channels) if tactile_channel is None else tactile_channel

    for channel in audio_targets:
        if 0 <= channel < channels:
            routed[:, channel] *= float(audio_volume)
    if 0 <= tactile_target < channels:
        routed[:, tactile_target] *= float(tactile_volume)
    return np.ascontiguousarray(routed)


def center_audio_for_output(data: np.ndarray, output_channels: int) -> np.ndarray:
    """Route mono/stereo instruction audio to auditory channels only."""
    array = ensure_2d_float32(data)
    if array.shape[1] == 1:
        mono = array[:, 0]
    else:
        mono = np.mean(array[:, :2], axis=1)

    routed = np.zeros((array.shape[0], output_channels), dtype=np.float32)
    if output_channels >= BINAURAL_TACTILE_CHANNELS:
        routed[:, 0] = mono
        routed[:, 1] = mono
    else:
        routed[:, 0] = mono
    return np.ascontiguousarray(routed)


def tactile_probe_for_output(data: np.ndarray, output_channels: int, tactile_volume: float = 1.0) -> np.ndarray:
    """Route a mono tactile probe to the active tactile output channel only."""
    array = ensure_2d_float32(data)
    tactile = array[:, 0]
    routed = np.zeros((array.shape[0], output_channels), dtype=np.float32)
    routed[:, tactile_output_channel_for_channels(output_channels)] = tactile * float(tactile_volume)
    return np.ascontiguousarray(routed)
