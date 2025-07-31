"""
Utility functions for data validation and preprocessing.
"""
import numpy as np
from xarray import DataArray
from typing import Set, Literal

from math import pi
from numpy.typing import ArrayLike

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


def xy2ll(
    x: ArrayLike,
    y: ArrayLike,
    sgn: Literal[1, -1],
    *args,
) -> tuple[ArrayLike, ArrayLike]:
    """Convert x y arrays to lat long arrays.

    Converts Polar  Stereographic (X, Y) coordinates for the polar regions to
    latitude and longitude Stereographic (X, Y) coordinates for the polar
    regions.
    Author: Michael P. Schodlok, December 2003 (map2xy.m)

    Parameters:
        - x: ArrayLike (float scalar or array)
        - y: ArrayLike (float scalar or array)
        - sgn (sign of latitude): integer (1 or -1) inidcating the hemisphere.
              1 : north latitude (default is mer = 45 lat = 70).
              -1 : south latitude (default is mer = 0  lat = 71).
        - *args: optional args. First optional arg is `delta` and second is
           `slat`. Review code for how these are used in practice.
    Returns:
        - (lat, lon)

    Usage:
        [lat, lon] = xy2ll(x, y, sgn)
        [lat, lon] = xy2ll(x, y, sgn, central_meridian, standard_parallel)
    """
    # Get central_meridian and standard_parallel depending on hemisphere
    if len(args) == 2:
        delta = args[0]
        slat = args[1]
    elif len(args) == 0:
        if sgn == 1:
            delta = 45.
            slat = 70.
            print(
                '       '
                ' xy2ll: creating coordinates in north polar stereographic'
                ' (Std Latitude: 70degN Meridian: 45deg)'
            )
        elif sgn == -1:
            delta = 0.
            slat = 71.
            print(
                '       '
                ' xy2ll: creating coordinates in south polar stereographic'
                ' (Std Latitude: 71degS Meridian: 0deg)'
            )
        else:
            raise ValueError('sgn should be either 1 or -1')
    else:
        raise Exception('bad usage: type "help(xy2ll)" for details')

    # if x, y passed as lists, convert to np.arrays
    if not np.issubdtype(type(x), np.ndarray):
        x = np.array(x)
    if not np.issubdtype(type(y), np.ndarray):
        y = np.array(y)

    # Conversion constant from degrees to radians
    # cde = 57.29577951
    # Radius of the earth in meters
    re = 6378.273 * 10**3
    # Eccentricity of the Hughes ellipsoid squared
    ex2 = .006693883
    # Eccentricity of the Hughes ellipsoid
    ex = np.sqrt(ex2)

    sl = slat * pi / 180.
    rho = np.sqrt(x**2 + y**2)
    cm = np.cos(sl) / np.sqrt(1.0 - ex2 * (np.sin(sl)**2))
    T = np.tan((pi / 4.0) - (sl / 2.0)) / ((1.0 - ex * np.sin(sl)) / (1.0 + ex * np.sin(sl)))**(ex / 2.0)

    if abs(slat - 90.) < 1.e-5:
        T = rho * np.sqrt((1. + ex)**(1. + ex) * (1. - ex)**(1. - ex)) / 2. / re
    else:
        T = rho * T / (re * cm)

    chi = (pi / 2.0) - 2.0 * np.arctan(T)
    lat = chi + ((ex2 / 2.0) + (5.0 * ex2**2.0 / 24.0) + (ex2**3.0 / 12.0)) * np.sin(2 * chi) + ((7.0 * ex2**2.0 / 48.0) + (29.0 * ex2**3 / 240.0)) * np.sin(4.0 * chi) + (7.0 * ex2**3.0 / 120.0) * np.sin(6.0 * chi)

    lat = sgn * lat
    lon = np.arctan2(sgn * x, -sgn * y)
    lon = sgn * lon

    res1 = np.nonzero(rho <= 0.1)[0]
    if len(res1) > 0:
        lat[res1] = pi / 2. * sgn
        lon[res1] = 0.0

    lon = lon * 180. / pi
    lat = lat * 180. / pi
    lon = lon - delta

    return lat, lon
    

def scale_factor(da: DataArray, sgn: int) -> DataArray:

    '''
    Calculates the area scale factor for a DataArray on a Polar Stereographic
    grid.

    Inputs:
        - da: DataArray with dimensions [x, y, ...]
        - sgn: integer indicating the hemisphere.
            +1 if North Pole
            -1 if South Pole
    Returns:
        - DataArray for k, the area scale factor (Geolzer et al., 2020)
    '''

    check_dims(da, {'x', 'y'})
    x = da.x
    y = da.y

    # centre origin on the pole if not already
    xs = x - x.mean()
    ys = y - y.mean()
 
    lat, _ = xy2ll(xs, ys, sgn)
    k = 2/(1+np.sin(sgn*lat*2*pi/360))

    return k


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
