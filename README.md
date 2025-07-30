# py-sle: Python Library for Sea Level Contribution Calculations

A Python library for calculating sea level contribution from ice sheet model output using the methodology from Goelzer et al. (2020).

## Features

- **High Performance**: Optimized dask-based parallelization with 46% speedup over naive implementations
- **Robust**: Memory-efficient processing with automatic resource management
- **Flexible**: Support for both single calculations and ensemble processing
- **Well-Tested**: Comprehensive benchmarking and validation
- **Easy to Use**: Simple API and command-line interface
- **Progress Tracking**: Built-in progress bars show chunk-level computation progress for both individual calculations and ensemble processing

## Installation

```bash
# Install from source
git clone https://github.com/your-username/py-sle.git
cd py-sle
pip install -e .

# Install with development dependencies
pip install -e ".[dev]"
```

## Quick Start

### Command Line Interface

```bash
# Basic usage
goelzer-slc thickness/ z_base/ output.nc --parallel

# With basin mask for regional analysis
goelzer-slc thickness/ z_base/ output.nc --mask basins.nc --parallel

# Custom parameters
goelzer-slc thickness/ z_base/ output.nc --rho-ice 917 --rho-ocean 1025 --parallel

# Disable progress bar for batch processing
goelzer-slc thickness/ z_base/ output.nc --parallel --no-progress
```

### Python API

```python
import py_sle
from pathlib import Path

# Simple calculation with chunk progress
calculator = py_sle.SLCCalculator(show_progress=True)
slc_grid = calculator.calculate_slc(thickness_data, z_base_data)

# Ensemble processing with context manager and progress bars
with py_sle.EnsembleProcessor(parallel=True, show_progress=True) as processor:
    results = processor.process_ensemble(
        thickness_dir=Path("thickness/"),
        z_base_dir=Path("z_base/"),
        mask_file=Path("basin_mask.nc")
    )
    
    processor.save_results(results, "ensemble_slc.nc")

# Disable progress bars for batch processing
processor = py_sle.EnsembleProcessor(parallel=True, show_progress=False)
```

## Performance

The library includes optimized configurations based on extensive benchmarking:

- **Optimal chunking**: 192×192 spatial chunks with 98 time chunks
- **Parallel workers**: 4 workers × 2 threads for 8-core systems  
- **Memory management**: 2GB limits per worker to prevent crashes
- **~46% speedup** over naive implementations

## Progress Tracking

The library provides comprehensive progress tracking for long-running calculations:

### Chunk-Level Progress
- **Dask Progress Bars**: Shows progress of individual chunk computations
- **Component Tracking**: Separate progress bars for each SLC component (VAF, POV, Density Correction)
- **Real-time Updates**: Live progress updates with completion percentages and timing

### Ensemble Progress  
- **File Processing**: Simple text-based progress through ensemble member files
- **Status Updates**: Shows current file being processed and processing stage
- **Configurable**: Can be disabled with `--no-progress` flag or `show_progress=False`

```python
# Enable detailed progress tracking
calculator = py_sle.SLCCalculator(show_progress=True)
# Shows: "Calculating VAF component..." with [####....] progress bar

# Ensemble with progress
processor = py_sle.EnsembleProcessor(show_progress=True)
# Shows: "Processing ensemble run 1/10: model_001.nc"
```

## API Reference

### Core Classes

- `SLCCalculator`: Core sea level contribution calculations
- `EnsembleProcessor`: Batch processing for multiple model runs

### Utility Functions

- `check_alignment()`: Validate data array alignment
- `check_dims()`: Validate required dimensions
- `scale_factor()`: Calculate polar projection scale factors

## Methodology

Based on Goelzer et al. (2020) methodology calculating three components:

1. **Volume Above Floatation (VAF)**: Changes in grounded ice volume
2. **Potential Ocean Volume (POV)**: Changes in bed topography below sea level
3. **Density Correction**: Accounting for floating ice density differences

## Requirements

- Python ≥ 3.9
- numpy ≥ 1.21.0
- xarray ≥ 2022.3.0  
- dask[distributed] ≥ 2022.3.0
- netcdf4 ≥ 1.5.0

## Development

```bash
# Install development dependencies
pip install -e ".[dev]"

# Run tests
pytest

# Code formatting
black py_sle/
flake8 py_sle/

# Type checking
mypy py_sle/
```

## References

Goelzer, H., et al. (2020). The future sea-level contribution of the Greenland ice sheet: a multi-model ensemble study of ISMIP6. *The Cryosphere*, 14, 833-860. https://doi.org/10.5194/tc-14-833-2020

## License

MIT License - see LICENSE file for details.

## Contributing

Contributions welcome! Please see CONTRIBUTING.md for guidelines.
