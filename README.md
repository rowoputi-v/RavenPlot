# ⚡ Harry Plotter

A modern HDF5 signal viewer for Linux, built with Python, Tkinter, and Matplotlib.

![Harry Plotter Screenshot](image-2024-12-4_11-28-24.png)

## Features

- **Browse & search** all datasets inside one or more HDF5 files in a clean sidebar tree
- **Additive plotting** — click signals one by one to stack them vertically for comparison
- **Multi-file support** — open a base file then use *Add File* to load signals from additional HDF5 files side-by-side
- **Overlay mode** — plot multiple selected signals on a single shared axes
- **Drag & drop** — drop one or more `.h5` / `.hdf5` / `.hdf` files directly onto the window
- **GPS map** — renders a GPS track from `latitude`/`longitude` datasets in the browser via Folium
- **Navigation toolbar** — pan, zoom, save each individual plot
- **Responsive** — plots redraw when the window is resized
- **Catppuccin Mocha** dark theme throughout

## Requirements

- Python 3.9+
- `h5py`
- `numpy`
- `matplotlib`
- `tkinterdnd2` *(optional — enables drag & drop)*
- `mplcursors` *(optional — enables hover tooltips on plots)*
- `folium` *(optional — enables GPS map feature)*

## Installation

```bash
git clone https://github.com/rowoputi-v/HarryPlotterClone_Linux.git
cd HarryPlotterClone_Linux

python -m venv .venv
source .venv/bin/activate

pip install h5py numpy matplotlib tkinterdnd2 mplcursors folium
```

## Running

```bash
./run.sh
```

Or directly:

```bash
.venv/bin/python harryplotter.py
```

## Usage

| Action | How |
|---|---|
| Open a file | Click **Open HDF5** or drag & drop |
| Add a second file | Click **Add File** |
| Plot a signal | Click it in the tree |
| Stack another signal below | Click another signal |
| Multi-select | Ctrl+click / Shift+click, then **▶ Plot Selected** |
| Overlay signals | Enable **Overlay** checkbox, then plot |
| Clear all plots | Click **Clear Plots** or `Ctrl+L` |
| Open file dialog | `Ctrl+O` |

## Project Structure

```
harryplotter.py   # Main application
run.sh            # Launch script
icons/            # App icon
.venv/            # Python virtual environment (not committed)
```

## License

MIT
