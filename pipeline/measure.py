"""Reads every frame of the two NASA videos and measures what is on screen.

Writes one CSV per video to pipeline/out and the timelines the website plays from to data/.

    python pipeline/measure.py path/to/videos
"""
import json
import subprocess
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "pipeline" / "out"
FPS = 30


def frames(path, w, h):
    cmd = ["ffmpeg", "-v", "error", "-i", str(path), "-vf", f"scale={w}:{h}",
           "-f", "rawvideo", "-pix_fmt", "rgb24", "-"]
    p = subprocess.Popen(cmd, stdout=subprocess.PIPE)
    size = w * h * 3
    while (buf := p.stdout.read(size)) and len(buf) == size:
        yield np.frombuffer(buf, np.uint8).reshape(h, w, 3).astype(np.int16)


def hue_masks(r, g, b):
    # purple marks light gained, orange marks light lost on NASA's change map
    rf, gf, bf = r / 255, g / 255, b / 255
    mx = np.maximum(np.maximum(rf, gf), bf)
    d = mx - np.minimum(np.minimum(rf, gf), bf) + 1e-9
    h = np.where(mx == rf, ((gf - bf) / d) % 6, np.where(mx == gf, (bf - rf) / d + 2, (rf - gf) / d + 4)) * 60
    lit = (mx > 0.22) & (d / (mx + 1e-9) > 0.25)
    return lit & (h >= 240) & (h <= 310), lit & (h >= 15) & (h <= 48)


def norm(x):
    x = np.asarray(x, float)
    return (x - x.min()) / (x.max() - x.min())


def lightning(path):
    W, H = 640, 360
    yy, xx = np.mgrid[0:H, 0:W]
    dial = (xx > W * 0.85) & (yy > H * 0.75)
    rows = []
    for f in frames(path, W, H):
        r, g, b = f[..., 0], f[..., 1], f[..., 2]
        dots = (r > 150) & (g > 130) & (b < 90) & ~dial   # lightning is yellow, stars are white
        n = int(dots.sum())
        rows.append({
            "strikes_px": n,
            "centre_x": xx[dots].mean() / W if n else 0.5,
            "centre_y": yy[dots].mean() / H if n else 0.5,
        })
    df = pd.DataFrame(rows)
    df["t"] = df.index / FPS
    df["activity"] = norm(df.strikes_px)
    trend = df.strikes_px.rolling(45, center=True, min_periods=1).median()
    df["surge"] = ((df.strikes_px - trend) / (trend + 1)).clip(lower=0)

    # chapters and dates, read off the video itself
    first = df.index[df.strikes_px > 50].min()
    df["phase"] = np.select([df.index < first, df.t < 70, df.t <= 215.7], ["intro", "one_day", "years"], "outro")
    dial_readings = [(70, "2017-03-01"), (100, "2017-08-10"), (120, "2018-05-10"), (140, "2019-04-10"),
                     (160, "2020-08-10"), (180, "2021-12-01"), (200, "2023-01-20"), (215.7, "2023-07-31")]
    ts = [t for t, _ in dial_readings]
    ns = [pd.Timestamp(d).value for _, d in dial_readings]
    df["date"] = pd.to_datetime(np.interp(df.t, ts, ns).astype("int64")).strftime("%Y-%m-%d")
    df.loc[df.phase == "intro", "date"] = "intro"
    df.loc[df.phase == "one_day", "date"] = "2017-03-01 (one day, following the ISS)"
    return df


REGIONS = {  # inset boxes on the night lights video, as fractions of the frame
    "w_europe": (.095, .255, .40, .945),
    "e_med": (.312, .415, .11, .58),
    "ukraine": (.629, .715, .13, .336),
    "india": (.793, .918, .54, .96),
}
PHASES = [(0, 9.8, "world_years"), (9.8, 20.8, "world_change"), (20.8, 22.5, "zoom_in"),
          (22.5, 36.9, "regions_years"), (36.9, 99, "regions_change")]


def night_lights(path):
    W, H = 1920, 540
    rows = []
    for f in frames(path, W, H):
        r, g, b = f[..., 0], f[..., 1], f[..., 2]
        lum = 0.299 * r + 0.587 * g + 0.114 * b
        purple, orange = hue_masks(r, g, b)
        row = {"light_px": int(((lum > 70) & (abs(r - b) < 70)).sum()),
               "purple_px": int(purple.sum()), "orange_px": int(orange.sum())}
        for k, (x0, x1, y0, y1) in REGIONS.items():
            sl = (slice(int(y0 * H), int(y1 * H)), slice(int(x0 * W), int(x1 * W)))
            R, G, B, L = r[sl], g[sl], b[sl], lum[sl]
            p, o = hue_masks(R, G, B)
            row[f"{k}_glow"] = float(L[(L > 70) & (abs(R - B) < 70)].sum())
            row[f"{k}_purple"], row[f"{k}_orange"] = int(p.sum()), int(o.sum())
        rows.append(row)
    df = pd.DataFrame(rows)
    df["t"] = df.index / FPS
    df["phase"] = [next(p for a, b, p in PHASES if a <= t < b) for t in df.t]
    change = df.phase.isin(["world_change", "regions_change"])

    def growth(p, o):
        tot = p + o
        return np.where(change & (tot > 50), (p - o) / (tot + 1e-9), 0.0)

    df["glow"] = norm(df.light_px)
    df["growth_vs_loss"] = growth(df.purple_px, df.orange_px)
    for k in REGIONS:
        df[f"{k}_glow_n"] = df[f"{k}_glow"] / df[f"{k}_glow"].max()
        df[f"{k}_growth"] = growth(df[f"{k}_purple"], df[f"{k}_orange"])

    # the on-screen year label steps forward at these times
    world = [0.37 + 0.6 * i for i in range(11)]
    zoom = [25.0, 25.87, 27.0, 27.67, 28.27, 30.03, 30.63, 31.23, 31.8, 32.4, 33.0]
    def year(row):
        if row.phase == "world_years":
            return str(2012 + sum(row.t >= s for s in world))
        if row.phase == "regions_years":
            return str(2012 + sum(row.t >= s for s in zoom))
        return "2012 to 2023" if row.phase in ("world_change", "regions_change") else ""
    df["year"] = df.apply(year, axis=1)
    return df


def timeline(df, song_t, duration, cols, labels, chapters, track_id):
    ts = np.arange(0, duration, 0.1)
    idx = np.clip(np.searchsorted(song_t, ts), 0, len(df) - 1)
    return {
        "id": track_id, "duration": duration, "hz": 10,
        "fields": {c: np.round(np.interp(ts, song_t, df[c].astype(float)), 3).tolist() for c in cols},
        labels[0]: df[labels[1]].values[idx].tolist(),
        "chapters": chapters,
    }


if __name__ == "__main__":
    src = Path(sys.argv[1])
    OUT.mkdir(parents=True, exist_ok=True)

    L = lightning(src / "Lightning.mp4")
    L.to_csv(OUT / "lightning.csv", index=False)
    L["act"] = L.activity.rolling(30, center=True, min_periods=1).mean()
    lt = timeline(L, L.t.values, 216.7, ["act", "surge", "centre_x", "centre_y"], ("dates", "date"), [
        {"t": 0, "name": "Orbit", "describe": "The International Space Station circles the Earth. No lightning yet, so only the pad plays, quiet and dark."},
        {"t": 23, "name": "One day", "describe": "1 March 2017. As the station passes over each storm, a single chime rings. Higher notes mean storms further north."},
        {"t": 70.4, "name": "Six years", "describe": "The whole planet, 2017 to 2023. The beat drops in. More lightning opens the pad and fills the reverb, and sudden surges become hi-hat rolls."},
    ], "lightning")

    N = night_lights(src / "Night Lights.mp4")
    N.to_csv(OUT / "nightlights.csv", index=False)
    cols = ["glow", "growth_vs_loss"] + [c for k in REGIONS for c in (f"{k}_glow", f"{k}_growth")]
    for k in REGIONS:
        N[f"{k}_glow"] = N[f"{k}_glow_n"]
    nt = timeline(N, N.t.values * 2, 86.7, cols, ("years", "year"), [   # the video plays at half speed
        {"t": 0, "name": "The world, year by year", "describe": "City lights across the planet from 2012 to 2023. As the glow grows, the pad swells and brightens."},
        {"t": 19.6, "name": "What changed", "describe": "Purple marks new light since 2012 and orange marks light lost. Where the world grew brighter, the chords turn to their brighter Dorian colour."},
        {"t": 41.6, "name": "Four regions", "describe": "The beat arrives. Western Europe, the Eastern Mediterranean, Ukraine and India each get their own voice, as loud as their own lights."},
        {"t": 73.8, "name": "Gained and lost", "describe": "India gained the most light and its melody shines. Ukraine and Western Europe lost light, and the drums fall silent for them."},
    ], "nightlights")

    for t in (lt, nt):
        (ROOT / "data" / f"{t['id']}.json").write_text(json.dumps(t, separators=(",", ":")))
