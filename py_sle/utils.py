"""
Utility functions for data validation and preprocessing.
"""

from typing import Set
import numpy as np
from xarray import DataArray

from .constants import REQUIRED_DIMS


def check_alignment(da1: DataArray, da2: DataArray) -> None:
    """
    Check that two DataArrays have aligned coordinates.
    
    Parameters
    ----------
    da1, da2 : xarray.DataArray
        DataArrays to check for alignment
        
    Raises
    ------
    ValueError
        If DataArrays are not aligned
    """
    # Check dimensions match
    if da1.dims != da2.dims:
        raise ValueError(f"DataArrays have different dimensions: {da1.dims} vs {da2.dims}")
    
    # Check shapes match
    if da1.shape != da2.shape:
        raise ValueError(f"DataArrays have different shapes: {da1.shape} vs {da2.shape}")
    
    # Check coordinates match
    for dim in da1.dims:
        if not da1[dim].equals(da2[dim]):
            raise ValueError(f"DataArrays are not aligned along dimension '{dim}'")


def check_dims(da: DataArray, required_dims: Set[str]) -> None:
    """
    Check that a DataArray has the required dimensions.
    
    Parameters
    ----------
    da : xarray.DataArray
        DataArray to check
    required_dims : set of str
        Set of required dimension names
        
    Raises
    ------
    ValueError
        If required dimensions are missing
    """
    missing_dims = required_dims - set(da.dims)
    if missing_dims:
        raise ValueError(
            f"DataArray missing required dimensions: {missing_dims}. "
            f"Found dimensions: {set(da.dims)}"
        )


def scale_factor(da: DataArray, sgn: int = -1) -> float:
    """
    Calculate the area scale factor for polar stereographic projections.
    
    Parameters
    ----------
    da : xarray.DataArray
        DataArray with coordinate information
    sgn : int, optional
        Sign indicating hemisphere: -1 for Antarctic, +1 for Arctic
        
    Returns
    -------
    float
        Area scale factor
        
    Notes
    -----
    This is a simplified implementation. For more accurate calculations,
    consider using the full polar stereographic projection formulas.
    """
    # Simplified scale factor calculation
    # For Antarctic (sgn=-1), this is typically close to 1.0 near the pole
    # This should be replaced with proper polar stereographic calculations
    # based on your specific projection parameters
    
    if sgn == -1:  # Antarctic
        return 1.0  # Simplified for now
    else:  # Arctic
        return 1.0  # Simplified for now


def validate_input_data(thickness: DataArray, z_base: DataArray) -> None:
    """
    Validate input data arrays for SLC calculation.
    
    Parameters
    ----------
    thickness : xarray.DataArray
        Ice thickness data
    z_base : xarray.DataArray
        Bed elevation data
        
    Raises
    ------
    ValueError
        If data validation fails
    """
    # Check dimensions
    for da in (thickness, z_base):
        check_dims(da, REQUIRED_DIMS)
    
    # Check alignment
    check_alignment(thickness, z_base)
    
    # Check for reasonable data ranges
    if thickness.min() < 0:
        raise ValueError("Negative thickness values found")
        
    if np.abs(z_base).max() > 10000:  # 10km seems reasonable for bed elevation
        raise ValueError("Extreme bed elevation values found (>10km)")


def prepare_chunked_data(
    da: DataArray, 
    chunks: dict = None,
    parallel: bool = True
) -> DataArray:
    """
    Prepare DataArray with optimal chunking for parallel computation.
    
    Parameters
    ----------
    da : xarray.DataArray
        Input DataArray
    chunks : dict, optional
        Chunk sizes. If None, uses optimized defaults
    parallel : bool, optional
        Whether to apply chunking for parallel computation
        
    Returns
    -------
    xarray.DataArray
        Chunked DataArray ready for parallel computation
    """
    if not parallel:
        return da
        
    if chunks is None:
        from .constants import DEFAULT_CHUNKS
        chunks = {**DEFAULT_CHUNKS["spatial"], **DEFAULT_CHUNKS["temporal"]}
    
    return da.chunk(chunks)
