# 🐦 Raven Plot

A modern HDF5 signal viewer — web-based, powered by Flask and Plotly.

## Features

- **Browse & search** all datasets inside one or more HDF5 files
- **Expandable/collapsible** signal tree
- **Multi-file support** — load and compare signals across files
- **Plot types** — line, bar, scatter, step
- **Drag & drop** file loading
- **Clear file / Clear plots** controls
- Clean, Apple/Scandinavian-inspired dark UI

## Requirements

- Python 3.9+
- `flask`, `plotly`, `h5py`, `numpy`

## Installation

```bash
python -m venv .venv
source .venv/bin/activate
pip install flask plotly h5py numpy
```

## Running

```bash
cd webapp
./run_web.sh
```

Then open [http://localhost:5050](http://localhost:5050) in your browser.

## License

MIT
