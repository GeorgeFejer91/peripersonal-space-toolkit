"""Unified event fanout for PPS timing markers.

The local :class:`SessionEventLogger` remains the durable source of events.  If
``pylsl`` is installed, the same actual events are also emitted as an LSL marker
stream for LabRecorder/XDF capture.  Planned future events should be written to
the local logger only; LSL markers represent events at the moment they happen.
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass
from typing import Any

from .session_events import SessionEvent, SessionEventLogger


LSL_STREAM_NAME = "PPSMarkers"
LSL_STREAM_TYPE = "Markers"
LSL_SOURCE_ID_PREFIX = "pps-markers"


@dataclass(frozen=True)
class LSLStatus:
    available: bool
    enabled: bool
    stream_name: str = LSL_STREAM_NAME
    message: str = ""


class LSLMarkerOutlet:
    """Optional pylsl marker outlet with a small stable marker schema."""

    def __init__(self, *, session_id: str, participant_id: str):
        self.session_id = session_id
        self.participant_id = participant_id
        self.status = LSLStatus(available=False, enabled=False, message="pylsl is not installed.")
        self._outlet = None
        try:
            from pylsl import StreamInfo, StreamOutlet  # type: ignore
        except Exception as exc:
            self.status = LSLStatus(available=False, enabled=False, message=f"pylsl unavailable: {exc}")
            return

        try:
            info = StreamInfo(
                LSL_STREAM_NAME,
                LSL_STREAM_TYPE,
                3,
                0,
                "string",
                f"{LSL_SOURCE_ID_PREFIX}-{session_id}",
            )
            desc = info.desc()
            desc.append_child_value("session_id", session_id)
            desc.append_child_value("participant_id", participant_id)
            channels = desc.append_child("channels")
            for label in ("event_type", "event_id", "payload_json"):
                channel = channels.append_child("channel")
                channel.append_child_value("label", label)
                channel.append_child_value("type", "Marker")
            self._outlet = StreamOutlet(info)
            self.status = LSLStatus(available=True, enabled=True, message="LSL marker outlet active.")
        except Exception as exc:
            self.status = LSLStatus(available=True, enabled=False, message=f"Could not create LSL outlet: {exc}")

    def push(self, event: SessionEvent) -> None:
        if self._outlet is None:
            return
        payload_json = json.dumps(event.payload, sort_keys=True, ensure_ascii=False)
        self._outlet.push_sample([event.event_type, str(event.event_id), payload_json])


class TimingEventHub:
    """Fan out actual timing events to local logs and optional LSL."""

    def __init__(self, logger: SessionEventLogger, *, enable_lsl: bool, session_id: str, participant_id: str):
        self.logger = logger
        self.session_id = session_id
        self.participant_id = participant_id
        self.lsl: LSLMarkerOutlet | None = LSLMarkerOutlet(session_id=session_id, participant_id=participant_id) if enable_lsl else None

    @property
    def lsl_status(self) -> LSLStatus:
        if self.lsl is None:
            return LSLStatus(available=False, enabled=False, message="LSL disabled for this run.")
        return self.lsl.status

    def log(
        self,
        event_type: str,
        *,
        unix_time: float | None = None,
        monotonic_time: float | None = None,
        push_lsl: bool = True,
        **payload: Any,
    ) -> SessionEvent:
        if unix_time is None:
            unix_time = time.time()
        if monotonic_time is None:
            monotonic_time = time.perf_counter()
        payload.setdefault("session_id", self.session_id)
        payload.setdefault("participant_id", self.participant_id)
        event = self.logger.log(event_type, unix_time=unix_time, monotonic_time=monotonic_time, **payload)
        if push_lsl and self.lsl is not None:
            self.lsl.push(event)
        return event
