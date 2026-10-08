import wave

import numpy as np
import pytest

from app.ui.car import CarModel
from app.ui import sounds
from app.ui.sounds import SAMPLE_RATE, SoundMixer, engine, render_all, save_wav


def dominant_frequency(samples):

    spectrum = np.abs(np.fft.rfft(samples * np.hanning(len(samples))))
    freqs = np.fft.rfftfreq(len(samples), 1 / SAMPLE_RATE)

    return freqs[np.argmax(spectrum[5:]) + 5]


# ---------------------------------------------------------------
# Synthesis
# ---------------------------------------------------------------

def test_every_sound_is_valid_audio():

    all_sounds = render_all()

    assert set(all_sounds) == {
        "entry", "hover", "hide", "exit", "honk", "click", "wiper", "listen", "success",
    }

    for name, samples in all_sounds.items():

        assert samples.dtype == np.float32, name
        assert np.isfinite(samples).all(), name
        assert 0.05 < np.abs(samples).max() <= 1.0, name
        assert 0.04 < len(samples) / SAMPLE_RATE < 2.0, name


def test_the_engine_note_rises_with_the_revs():

    low = engine(0.6, [900, 900])
    high = engine(0.6, [3600, 3600])

    assert dominant_frequency(high[3000:9000]) > 2 * dominant_frequency(low[3000:9000])


def test_the_engine_follows_a_rev_curve():

    sound = engine(1.0, [900, 4500])

    early = dominant_frequency(sound[2000:6000])
    late = dominant_frequency(sound[-8000:-2000])

    assert late > early


def test_sounds_are_deterministic():

    assert np.array_equal(render_all()["exit"], render_all()["exit"])


def test_volume_scales_the_level():

    quiet, loud = render_all(volume=0.3)["honk"], render_all(volume=1.0)["honk"]

    assert np.abs(loud).max() > 2 * np.abs(quiet).max()


def test_wav_files_can_be_saved(tmp_path):

    path = tmp_path / "x.wav"

    save_wav(path, render_all()["honk"])

    with wave.open(str(path)) as f:

        assert f.getnchannels() == 1
        assert f.getframerate() == SAMPLE_RATE
        assert f.getnframes() == len(render_all()["honk"])


# ---------------------------------------------------------------
# Mixer
# ---------------------------------------------------------------

class FakeStream:

    def __init__(self, callback):
        self.callback = callback
        self.started = self.stopped = False

    def start(self):
        self.started = True

    def stop(self):
        self.stopped = True

    def close(self):
        pass

    def pull(self, frames):

        out = np.zeros((frames, 1), dtype="float32")

        self.callback(out, frames, None, None)

        return out[:, 0]


def make_mixer(sound_set=None, **kwargs):

    streams = []

    def factory(callback):

        stream = FakeStream(callback)
        streams.append(stream)

        return stream

    mixer = SoundMixer(
        stream_factory=factory,
        sounds=sound_set or {"a": np.full(100, 0.4, dtype="float32"), "b": np.full(50, 0.3, dtype="float32")},
        **kwargs,
    )

    return mixer, streams


def test_the_stream_opens_on_the_first_sound_only():

    mixer, streams = make_mixer()

    assert streams == []

    mixer.play("a")

    assert len(streams) == 1 and streams[0].started

    mixer.play("b")

    assert len(streams) == 1


def test_sounds_play_through_and_overlap():

    mixer, streams = make_mixer(volume=1.0)

    mixer.play("a")
    mixer.play("b")

    out = streams[0].pull(60)

    # both together first, then only "a"
    assert out[0] == pytest.approx(0.7)
    assert out[55] == pytest.approx(0.4)

    out = streams[0].pull(60)

    assert out[0] == pytest.approx(0.4) and out[45] == 0

    assert mixer._voices == []


def test_volume_and_clipping():

    mixer, streams = make_mixer(volume=0.5)

    mixer.play("a")

    assert streams[0].pull(10)[0] == pytest.approx(0.2)

    loud, loud_streams = make_mixer(
        sound_set={"x": np.full(10, 0.9, dtype="float32")}, volume=1.0
    )

    loud.play("x")
    loud.play("x")

    assert loud_streams[0].pull(10)[0] == 1.0


def test_disabled_muted_or_unknown_sounds_do_nothing():

    mixer, streams = make_mixer(enabled=False)

    mixer.play("a")

    assert streams == []

    mixer.set_enabled(True)
    mixer.play("nope")

    assert streams == []

    mixer.volume = 0
    mixer.play("a")

    assert streams == []


def test_muting_stops_whatever_is_playing():

    mixer, streams = make_mixer(volume=1.0)

    mixer.play("a")
    mixer.set_enabled(False)

    assert streams[0].pull(10).max() == 0


def test_no_audio_device_is_survived_quietly():

    def broken(callback):
        raise OSError("no output device")

    mixer = SoundMixer(stream_factory=broken, sounds={"a": np.ones(10, dtype="float32")})

    mixer.play("a")
    mixer.play("a")              # does not retry or raise

    assert mixer._failed and mixer._voices == []


def test_close_stops_the_stream():

    mixer, streams = make_mixer()

    mixer.play("a")
    mixer.close()

    assert streams[0].stopped


def test_the_preview_saves_wavs(tmp_path, monkeypatch):

    played = []

    class Silent:

        def __init__(self, sounds=None, **kwargs):
            pass

        def play(self, name):
            played.append(name)

        def close(self):
            pass

    monkeypatch.setattr(sounds, "SoundMixer", Silent)
    monkeypatch.setattr(sounds.time, "sleep", lambda s: None)

    sounds.main(["prog", str(tmp_path)])

    assert (tmp_path / "exit.wav").exists()
    assert played[0] == "entry" and "wiper" in played


# ---------------------------------------------------------------
# Wiper on the car
# ---------------------------------------------------------------

def run(car, seconds, dt=1 / 60):

    peak = 0.0

    for _ in range(int(seconds / dt)):

        car.step(dt)
        peak = max(peak, car.wiper)

    return peak


def test_a_parked_car_keeps_its_wiper_down():

    car = CarModel()

    assert run(car, 2) == 0.0


def test_a_wipe_sweeps_twice_then_parks():

    car = CarModel()

    car.kick("wipe")

    swept = []

    for _ in range(150):

        car.step(1 / 60)
        swept.append(car.wiper)

    peaks = sum(1 for a, b, c in zip(swept, swept[1:], swept[2:]) if b > a and b >= c and b > 0.8)

    assert peaks == 2

    run(car, 1.0)

    assert car.wiper < 0.02


def test_thinking_wipes_continuously_and_stops_when_done():

    car = CarModel()

    car.set_state("thinking")

    assert run(car, 3.0) > 0.9

    car.set_state("idle")

    run(car, 2.5)

    assert car.wiper < 0.02
