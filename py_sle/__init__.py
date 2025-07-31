"""
py-sle: Python library for calculating sea level contribution from ice sheet model output

This library provides tools to calculate sea level contribution from ice sheet 
thickness and bed elevation data using the methodology from Goelzer et al. (2020).
"""

__version__ = "1.0.0"
__author__ = "Jonnie Barnsley"

from .core import SLCCalculator
from .ensemble import EnsembleProcessor
from .utils import check_alignment, check_dims, scale_factor, prepare_chunked_data, load_areacell
from .constants import DEFAULT_DENSITIES, DEFAULT_OCEAN_AREA

__all__ = [
    "SLCCalculator",
    "EnsembleProcessor", 
    "check_alignment",
    "check_dims",
    "scale_factor",
    "prepare_chunked_data",
    "load_areacell",
    "DEFAULT_DENSITIES",
    "DEFAULT_OCEAN_AREA",
]
