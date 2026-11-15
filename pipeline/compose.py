"""Turns the measurements into MIDI for Logic Pro.

G minor, 88.6 BPM: the tempo at which the lightning video is exactly 80 bars
and the night lights video, at half speed, exactly 32.

    python pipeline/compose.py
"""
from pathlib import Path

import numpy as np
import pandas as pd
import pretty_midi as pm

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "pipeline" / "out"
MIDI = ROOT / "midi"

BPM = 88.6
SPB = 60 / BPM
BAR = 4 * SPB

CHORDS = {
    "Gm9": [55, 58, 62, 65, 69],
    "Ebmaj7": [51, 55, 58, 62, 65],
    "Cm9": [48, 51, 55, 58, 62],
    "C9": [48, 52, 55, 58, 62],     # the brighter Dorian version, used where light grew
    "Dm7": [50, 53, 57, 60, 64],
}
ROOTS = {"Gm9": 31, "Ebmaj7": 27, "Cm9": 36, "C9": 36, "Dm7": 26}
LOOP = ["Gm9", "Ebmaj7", "Cm9", "Dm7"]
PENTA = [0, 3, 5, 7, 10]            # G minor pentatonic
KICK, CLAP, HAT, OPEN_HAT = 36, 39, 42, 46


def penta(x, low=67, octaves=2):
    notes = [low + 12 * o + p for o in range(octaves) for p in PENTA] + [low + 12 * octaves]
    return notes[int(np.clip(x, 0, 0.999) * len(notes))]


def note(inst, pitch, start, end, vel):
    inst.notes.append(pm.Note(int(np.clip(vel, 1, 127)), int(pitch), float(start), float(end)))


def cc(inst, num, t, value):
    inst.control_changes.append(pm.ControlChange(num, int(np.clip(value, 0, 127)), float(t)))


def at(df, col, t):
    return df[col].values[min(np.searchsorted(df.st.values, t), len(df) - 1)]


def lightning():
    L = pd.read_csv(OUT / "lightning.csv")
    L["st"] = L.t
    L["act"] = L.activity.rolling(30, center=True, min_periods=1).mean()
    drop = round(70 / BAR)
    pad, keys, bass = pm.Instrument(0, name="Pad"), pm.Instrument(4, name="Rhodes"), pm.Instrument(38, name="808")
    drums = pm.Instrument(0, is_drum=True, name="Drums")
    chimes, voice = pm.Instrument(10, name="Chimes"), pm.Instrument(52, name="Voice")

    for bar in range(80):
        t0, chord = bar * BAR, LOOP[bar % 4]
        a = at(L, "act", t0 + BAR / 2)
        for p in CHORDS[chord]:
            note(pad, p, t0, t0 + BAR, 45 + 60 * a)
        if bar < drop:
            continue
        for off, length in [(0, 1.5), (1.5, 2.5)]:
            for p in CHORDS[chord][1:]:
                note(keys, p + 12, t0 + off * SPB, t0 + (off + length) * SPB, 50 + 50 * a)
        # busy storms: the 808 overlaps the next chord so it glides, and the pickup jumps an octave
        r = ROOTS[chord]
        note(bass, r, t0, t0 + (3.6 if a > 0.6 else 2.5) * SPB, 100)
        note(bass, r + (12 if a > 0.6 else 0), t0 + 3.5 * SPB, t0 + 4 * SPB, 85)

        note(drums, KICK, t0, t0 + 0.1, 115)
        if a > 0.45:
            note(drums, KICK, t0 + 2.75 * SPB, t0 + 2.85 * SPB, 90)
        note(drums, CLAP, t0 + 2 * SPB, t0 + 2 * SPB + 0.1, 105)
        seg = L[(L.st >= t0) & (L.st < t0 + BAR)]
        roll = int((seg.st.values[seg.surge.values.argmax()] - t0) // SPB) if seg.surge.max() > 0.25 else None
        for k in range(8):
            ht = t0 + k * 0.5 * SPB
            if k // 2 == roll:
                if k % 2 == 0:
                    for j in range(8):
                        note(drums, HAT, ht + j * SPB / 8, ht + j * SPB / 8 + 0.03, 40 + j * (6 + 8 * min(seg.surge.max(), 1)))
            else:
                note(drums, HAT, ht, ht + 0.05, 55 + (12 if k % 2 == 0 else 0) + 20 * a)
        if a > 0.7:
            note(drums, OPEN_HAT, t0 + 3.5 * SPB, t0 + 3.9 * SPB, 70)

    for t in np.arange(0, 80 * BAR, BAR / 16):
        a = at(L, "act", t)
        cc(pad, 1, t, 20 + 107 * a)
        cc(pad, 11, t, 70 + 57 * a)

    # chapter one: a chime for each storm the station passes over
    one = L[L.phase == "one_day"].copy()
    one["rise"] = one.strikes_px.diff(8).clip(lower=0)
    top, last = one.rise.quantile(0.93), -9
    for _, r in one[one.rise > top].iterrows():
        q = round(r.st / (SPB / 4)) * SPB / 4
        if q - last < SPB:
            continue
        last = q
        note(chimes, penta(1 - r.centre_y), q, q + 2 * SPB, 60 + 50 * min(r.rise / (top * 3), 1))
        cc(chimes, 10, q, 127 * r.centre_x)

    # chapter two: voice on the off-beats, pitch from latitude, pan from longitude
    for bar in range(drop, 80):
        for beat in range(4):
            t = bar * BAR + (beat + 0.5) * SPB
            a = at(L, "act", t)
            if a < 0.3 or (beat % 2 == 0 and a < 0.55):
                continue
            cc(voice, 10, t - 0.01, 127 * np.clip((at(L, "centre_x", t) - 0.3) / 0.4, 0, 1))
            note(voice, penta(np.clip((0.75 - at(L, "centre_y", t)) / 0.5, 0, 1), octaves=1), t, t + 0.45 * SPB, 70 + 40 * a)

    m = pm.PrettyMIDI(initial_tempo=BPM)
    m.instruments += [pad, keys, bass, drums, chimes, voice]
    m.write(str(MIDI / "lightning.mid"))


def night_lights():
    N = pd.read_csv(OUT / "nightlights.csv")
    N["st"] = N.t * 2
    pad, bass = pm.Instrument(89, name="Strings: city glow, Ukraine drone"), pm.Instrument(38, name="808")
    drums = pm.Instrument(0, is_drum=True, name="Drums")
    rhodes, bells, voice = (pm.Instrument(10, name="Rhodes: India"), pm.Instrument(11, name="Bells: Eastern Mediterranean"),
                            pm.Instrument(48, name="Voice: Western Europe"))

    for bar in range(32):
        t0, mid = bar * BAR, bar * BAR + BAR / 2
        phase, chord = at(N, "phase", mid), LOOP[bar % 4]
        if chord == "Cm9" and at(N, "growth_vs_loss", mid) > 0.15:
            chord = "C9"
        if phase != "zoom_in":
            for p in CHORDS[chord]:
                note(pad, p, t0, t0 + BAR, 50 + 50 * at(N, "glow", mid))
        regional = phase in ("regions_years", "regions_change")
        lost = phase == "regions_change" and min(at(N, "w_europe_growth", mid), at(N, "ukraine_growth", mid)) < -0.3
        if regional and not (lost and bar < 30):
            note(bass, ROOTS[chord], t0, t0 + 3 * SPB, 100)
            note(drums, KICK, t0, t0 + 0.1, 112)
            note(drums, CLAP, t0 + 2 * SPB, t0 + 2 * SPB + 0.1, 100)
            for k in range(8):
                note(drums, HAT, t0 + k * 0.5 * SPB, t0 + k * 0.5 * SPB + 0.05, 50 + 10 * (k % 2 == 0))
        if not regional:
            continue
        def vel(k):
            return (40 + 70 * at(N, f"{k}_glow_n", mid)) * (1 + 0.5 * at(N, f"{k}_growth", mid))
        for j in range(8):
            note(rhodes, penta((j / 8 + at(N, "india_glow_n", mid)) % 1, low=74, octaves=1),
                 t0 + j * 0.5 * SPB, t0 + (j * 0.5 + 0.4) * SPB, vel("india"))
        for b in (0, 2):
            note(bells, CHORDS[chord][3] + 12, t0 + b * SPB, t0 + (b + 1.5) * SPB, vel("e_med"))
        note(voice, CHORDS[chord][2] + 12, t0, t0 + BAR, vel("w_europe"))
        note(pad, 43, t0, t0 + BAR, vel("ukraine"))

    for t in np.arange(0, 32 * BAR, BAR / 16):
        cc(pad, 1, t, 15 + 112 * at(N, "glow", t))

    m = pm.PrettyMIDI(initial_tempo=BPM)
    m.instruments += [pad, rhodes, bass, drums, bells, voice]
    m.write(str(MIDI / "nightlights.mid"))


if __name__ == "__main__":
    MIDI.mkdir(exist_ok=True)
    lightning()
    night_lights()
