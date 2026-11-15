# nāda

A project for the 2026 NASA Space Apps Challenge, made for the challenge The Earth Information Jukebox. Two NASA visualisations of the Earth at night are measured frame by frame, and their data writes two R&B tracks, lightning and night lights. A website plays each track over its video and mixes the stems live from the same data.

Live site: https://sharvaripb.github.io/nada/

### The data

| Track | NASA source | What it shows |
|---|---|---|
| lightning | [Lightning from Space](https://svs.gsfc.nasa.gov/5011) (SVS 5011) | Lightning seen by the Lightning Imaging Sensor on the International Space Station, one day in March 2017 and then 2017 to 2023 |
| night lights | [Night Lights Change](https://svs.gsfc.nasa.gov/5313) (SVS 5313) | City lights from NASA's Black Marble product (VIIRS), 2012 to 2023, and where light was gained or lost |

Lightning data from ISS LIS is used to study how storms form and develop and how lightning relates to the atmosphere and climate ([NASA GHRC](https://ghrc.nsstc.nasa.gov/lightning/overview_lis_instrument.html)). Black Marble tracks human activity on the ground at night, including the growth of cities, the spread of electricity and power outages after conflict or disaster, and is used to support decisions on energy and sustainable development ([NASA Black Marble](https://blackmarble.gsfc.nasa.gov/)).

### How it works

- `pipeline/measure.py` reads every frame of both videos with ffmpeg and counts pixels by colour: lightning activity, sudden surges, where the storms sit on the globe, city glow, and light gained (purple) against light lost (orange) for four regions.
- `pipeline/compose.py` turns those measurements into MIDI at 88.6 BPM in G minor. Each measurement drives one musical decision once it crosses a fixed threshold, for example a hi-hat roll when lightning jumps 25% above its recent level.
- The MIDI was arranged and produced in Logic Pro, and the stems were exported for the site.
- `js/engine.js` plays the stems in sync with the video in the browser and keeps changing the mix from the data: filter, reverb, panning and, for night lights, a level for each region.

### Limits

The measurements are relative to each video rather than absolute counts, and the globe rotates, so storm position is read from what is in view.

### Run

The site is static. Serve the folder and open it in a browser:

```
python3 -m http.server
```

To rebuild the data and MIDI, put `Lightning.mp4` and `Night Lights.mp4` from the NASA pages above in a folder, then:

```
pip install -r requirements.txt
python3 pipeline/measure.py path/to/videos
python3 pipeline/compose.py
```

ffmpeg needs to be installed.

AI tools (Claude) were used to help write the code and the measurement scripts. The music was produced, mixed and arranged by me.

Visualisations and data courtesy of NASA's Scientific Visualization Studio. NASA does not endorse this project.
