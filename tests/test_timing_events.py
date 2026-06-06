from __future__ import annotations

import sys
import types

from peripersonal_space_toolkit.session_events import SessionEventLogger
from peripersonal_space_toolkit.timing_events import TimingEventHub


class _FakeDesc:
    def append_child_value(self, _key, _value):
        return self

    def append_child(self, _key):
        return self


class _FakeStreamInfo:
    def __init__(self, *args):
        self.args = args
        self._desc = _FakeDesc()

    def desc(self):
        return self._desc


class _FakeStreamOutlet:
    instances = []

    def __init__(self, info):
        self.info = info
        self.samples = []
        _FakeStreamOutlet.instances.append(self)

    def push_sample(self, sample):
        self.samples.append(sample)


def test_timing_event_hub_fans_out_to_logger_and_lsl(monkeypatch):
    _FakeStreamOutlet.instances.clear()
    fake_pylsl = types.SimpleNamespace(StreamInfo=_FakeStreamInfo, StreamOutlet=_FakeStreamOutlet)
    monkeypatch.setitem(sys.modules, "pylsl", fake_pylsl)
    logger = SessionEventLogger("P001")
    hub = TimingEventHub(logger, enable_lsl=True, session_id="S001", participant_id="P001")

    event = hub.log("mouse_click", x=10, y=20)

    assert hub.lsl_status.enabled
    assert logger.events == [event]
    assert _FakeStreamOutlet.instances
    assert _FakeStreamOutlet.instances[0].samples[0][0] == "mouse_click"
    assert _FakeStreamOutlet.instances[0].samples[0][1] == str(event.event_id)
    assert '"x": 10' in _FakeStreamOutlet.instances[0].samples[0][2]


def test_timing_event_hub_keeps_running_without_pylsl(monkeypatch):
    monkeypatch.setitem(sys.modules, "pylsl", None)
    logger = SessionEventLogger("P001")
    hub = TimingEventHub(logger, enable_lsl=True, session_id="S001", participant_id="P001")

    event = hub.log("session_start")

    assert not hub.lsl_status.enabled
    assert logger.events == [event]
