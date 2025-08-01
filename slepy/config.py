"""
Configuration parser for slepy.

Reads configuration from config.yaml if present, otherwise uses hardcoded defaults.
This allows for both customizable installations (git clone + config + pip install -e .)
and standard PyPI installations that work out of the box.
"""

import yaml
from pathlib import Path
from typing import Dict, Any


def _get_hardcoded_defaults() -> Dict[str, Any]:
    """Fallback hardcoded defaults if no config file is found."""
    return {
        "densities": {
            "ice": 918.0,
            "ocean": 1028.0,
            "water": 1000.0,
        },
        "ocean_area": 3.625e14,
        "chunks": {
            "spatial": {"x": 192, "y": 192},
            "temporal": {"time": 98},
        },
        "dask": {
            "n_workers": 4,
            "threads_per_worker": 2,
            "memory_limit": "2GB",
            "dashboard_address": None,
        },
        "variable_names": {
            "thickness": "thickness",
            "bed_elevation": "Z_base",
            "grounded_fraction": "grounded_fraction",
            "basin": "basin",
        }
    }


def load_config() -> Dict[str, Any]:
    """
    Load configuration from config.yaml if it exists, otherwise use defaults.
    
    Returns
    -------
    dict
        Configuration dictionary with all parameters
    """
    # Look for config.yaml in the package parent directory
    config_path = Path(__file__).parent.parent / "config.yaml"
    
    if config_path.exists():
        try:
            with open(config_path, 'r') as f:
                config = yaml.safe_load(f)
            return config
        except Exception as e:
            print(f"Warning: Could not load config.yaml ({e}). Using defaults.")
            return _get_hardcoded_defaults()
    else:
        # No config file - use hardcoded defaults
        return _get_hardcoded_defaults()


# Load configuration once when module is imported
_CONFIG = load_config()

# Export the same interface as the old defaults.py
DEFAULT_DENSITIES: Dict[str, float] = _CONFIG["densities"]
DEFAULT_OCEAN_AREA: float = _CONFIG["ocean_area"]
REQUIRED_DIMS = {"x", "y", "time"}  # This shouldn't be configurable
DEFAULT_CHUNKS = _CONFIG["chunks"] 
DEFAULT_DASK_CONFIG = _CONFIG["dask"]
DEFAULT_VARNAMES = _CONFIG["variable_names"]
