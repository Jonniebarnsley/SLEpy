# SLEpy

*/ˈslɛpi/*

A Python library for calculating sea level equivalent (SLE) from ice sheet model output using the methodology from [Goelzer et al. (2020)](https://doi.org/10.5194/tc-14-833-2020).

## Installation

```bash
# 1. Clone the repository
git clone https://github.com/Jonniebarnsley/SLEpy.git
cd SLEpy

# 2. (Optional) Customize defaults by editing config.yaml

# 3. Create and activate virtual environment
python -m venv slepy-env
source slepy-env/bin/activate  # On Windows: slepy-env\Scripts\activate

# 4. Install slepy and dependencies
pip install -e .
```

**Note:** After installation, the `slepy` command will be available in your terminal.

## Quick Start

SLEpy provides tools for calculating sea level equivalent both for a single model run and for model ensembles. It requires netcdf data for ice thickness with dimensions `(x, y, time)` and bed elevation with dimensions `(x, y)` or `(x, y, time)`. The ensemble processor assumes a directory structure similar to:
```
data/
├── thickness/
│   ├── run01_thickness.nc
│   ├── run02_thickness.nc
|   └── ...
└── z_base/
    ├── run01_Z_base.nc
    ├── run02_Z_base.nc
    └── ...
```

### Command Line Interface

```bash
# Basic usage
slepy thickness/ z_base/ output.nc

# With basin mask for regional analysis
slepy thickness/ z_base/ output.nc --mask basins.nc

# Custom parameters
slepy thickness/ z_base/ output.nc --rho-ice 917 --rho-ocean 1025
```

### Python API

```python
from slepy import SLECalculator, EnsembleProcessor

# Simple calculation on xarray DataArray objects
with SLECalculator() as calc:
    sle_grid = calc.calculate_sle(thickness_da, z_base_da)
    sle = sle_grid.sum(dim=['x', 'y'])

# Ensemble processing data directories
with EnsembleProcessor() as processor:
    results = processor.process_ensemble("thickness/", "z_base/", mask_file="basins.nc")
    processor.save_results(results, "ensemble_sle.nc")
```

## Advanced Usage

### Custom Variable Names

By default, the library expects specific variable names in your netCDF files. However, you can customize these to match your data:

#### Default Variable Names
- `thickness`: Ice thickness
- `Z_base`: Bed elevation 
- `grounded_fraction`: Grounded fraction (0=floating, 1=grounded)
- `basin`: Basin mask for regional analysis

#### Python API

```python
# Define custom variable names
custom_varnames = {
    'thickness': 'thk',
    'bed_elevation': 'bed'
}

# Use with EnsembleProcessor
with EnsembleProcessor(varnames=custom_varnames) as processor:
    results = processor.process_ensemble(thickness_dir="thickness/", z_base_dir="z_base/")
```

#### Command Line Interface

```bash
# Override specific variable names
slepy data/ data/ output.nc --thickness-var thk

# Multiple overrides
slepy data/ data/ output.nc \
    --thickness-var ice_thickness \
    --bed-elevation-var bedrock_elevation \
    --basin-var drainage_basins
```

### Using Grounded Fraction Data

If you have pre-calculated grounded fraction data, you can use it instead of letting the library calculate it using the floatation criteria:

#### Python API

```python
import xarray as xr

# Load your grounded fraction data
grounded_frac_da = xr.open_dataarray("grounded_fraction.nc")

# Use with SLECalculator
with SLECalculator() as calc:
    sle_grid = calc.calculate_sle(
        thickness=thickness_da, 
        z_base=z_base_da,
        grounded_fraction=grounded_frac_da
    )

# Use with EnsembleProcessor - grounded fraction files should be in a directory
# with the same naming pattern as thickness/z_base files
with EnsembleProcessor() as processor:
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