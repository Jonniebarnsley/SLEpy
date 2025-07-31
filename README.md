# SLEpy: Python Library for Sea Level Equivalent Calculations

A Python library for calculating sea level equivalent from ice sheet model output using the methodology from Goelzer et al. (2020).

## Installation

### Option 1: Virtual Environment (Recommended)

```bash
# Clone the repository
git clone https://github.com/Jonniebarnsley/SLEpy.git
cd SLEpy

# Create and activate virtual environment
python -m venv slepy-env
source slepy-env/bin/activate  # On Windows: slepy-env\Scripts\activate

# Install slepy and dependencies
pip install -e .
```

**Note:** After installation, the `slepy` command will be available in your terminal.

## Quick Start

### Command Line Interface

```bash
# Basic usage
slepy thickness/ z_base/ output.nc

# With basin mask for regional analysis
slepy thickness/ z_base/ output.nc --mask basins.nc

# Custom parameters
slepy thickness/ z_base/ output.nc --rho-ice 917 --rho-ocean 1025

# Disable progress bar for batch processing
slepy thickness/ z_base/ output.nc --no-progress
```

### Python API

```python
from slepy import SLECalculator, EnsembleProcessor
from pathlib import Path

# Simple calculation with proper resource management
with SLECalculator() as calculator:
    sle_grid = calculator.calculate_sle(thickness_data, z_base_data)

# Ensemble processing with context manager and progress bars
with EnsembleProcessor() as processor:
    results = processor.process_ensemble(
        thickness_dir=Path("thickness/"),
        z_base_dir=Path("z_base/"),
        mask_file=Path("basin_mask.nc")
    )
    
    processor.save_results(results, "ensemble_sle.nc")

# For batch processing without progress bars
with slepy.EnsembleProcessor(quiet=True) as processor:
    results = processor.process_ensemble(
        thickness_dir=Path("thickness/"),
        z_base_dir=Path("z_base/")
    )
```

## Advanced Usage

### Custom Variable Names

By default, the library expects specific variable names in your netCDF files. However, you can customize these to match your data:

#### Default Variable Names
- `thickness`: Ice thickness
- `Z_base`: Bed elevation 
- `grounded_fraction`: Grounded fraction (0=floating, 1=grounded)
- `basin`: Basin mask for regional analysis

**Note:** The time dimension must be named `time` - this cannot be customized.

#### Python API

```python
# Define custom variable names (partial override)
custom_varnames = {
    'thickness': 'thk',
    'bed_elevation': 'bed'
}

# Use with EnsembleProcessor
with EnsembleProcessor(varnames=custom_varnames) as processor:
    results = processor.process_ensemble(thickness_dir="data/", z_base_dir="data/")
```

#### Command Line Interface

```bash
# Override specific variable names
slepy data/ data/ output.nc --thickness-var thk --bed-elevation-var bed

# Multiple overrides
slepy data/ data/ output.nc \
    --thickness-var ice_thickness \
    --bed-elevation-var bedrock_elevation \
    --grounded-fraction-var gl_mask \
    --basin-var drainage_basins
```

### Using Grounded Fraction Data

If you have pre-calculated grounded fraction data, you can use it instead of letting the library calculate it from floatation criteria:

#### Python API

```python
import xarray as xr

# Load your grounded fraction data
grounded_frac = xr.open_dataarray("grounded_fraction.nc")

# Use with SLECalculator
with slepy.SLECalculator() as calculator:
    sle_grid = calculator.calculate_sle(
        thickness=thickness_data, 
        z_base=z_base_data,
        grounded_fraction=grounded_frac
    )

# Use with EnsembleProcessor - grounded fraction files should be in a directory
# with the same naming pattern as thickness/z_base files
with slepy.EnsembleProcessor() as processor:
    results = processor.process_ensemble(
        thickness_dir="thickness/",
        z_base_dir="z_base/", 
        grounded_fraction_dir="grounded_fraction/"
    )
```

#### Command Line Interface

```bash
# Specify grounded fraction directory
slepy thickness/ z_base/ output.nc --grounded-fraction-dir grounded_fraction/

# With custom variable name
slepy thickness/ z_base/ output.nc \
    --grounded-fraction-dir grounded_fraction/ \
    --grounded-fraction-var gl_mask
```

#### Grounded Fraction Data Requirements

- **Values**: Should be between 0 (fully floating) and 1 (fully grounded)
- **Dimensions**: Must match thickness and z_base data (x, y, time)
- **File naming**: For ensemble processing, files should follow the same naming pattern as thickness/z_base files
- **Variable name**: Default is `grounded_fraction`, but can be customized

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

## References

Goelzer, H., Coulon, V., Pattyn, F., de Boer, B., and van de Wal, R.: Brief communication: On calculating the sea-level contribution in marine ice-sheet models , The Cryosphere, 14, 833–840, https://doi.org/10.5194/tc-14-833-2020, 2020.

## License

MIT License - see LICENSE file for details.