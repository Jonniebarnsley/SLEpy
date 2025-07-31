"""
Physical constants and default parameters for sea level calculations.
"""

from typing import Dict

# Default physical constants
DEFAULT_DENSITIES: Dict[str, float] = {
    "ice": 918.0,      # kg m^-3, density of ice
    "ocean": 1028.0,   # kg m^-3, density of seawater  
    "water": 1000.0,   # kg m^-3, density of freshwater
}

# Ocean surface area (Gregory et al., 2019)
DEFAULT_OCEAN_AREA: float = 3.625e14  # m^2

# Coordinate dimension names
REQUIRED_DIMS = {"x", "y", "time"}

# Default chunk sizes (optimized for 8-core systems)
DEFAULT_CHUNKS = {
    "spatial": {"x": 192, "y": 192},
    "temporal": {"time": 98},
}

# Default worker configuration for dask
DEFAULT_DASK_CONFIG = {
    "n_workers": 4,
    "threads_per_worker": 2,
    "memory_limit": "2GB",
    "dashboard_address": None,
}

# Default variable names in netCDF files
DEFAULT_VARNAMES = {
    "thickness": "thickness",
    "bed_elevation": "Z_base", 
    "grounded_fraction": "grounded_fraction",
    "basin": "basin",
}
