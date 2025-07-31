"""
Core sea level contribution calculations based on Goelzer et al. (2020).
"""
import numpy as np
from typing import Dict
from xarray import DataArray
from dask.distributed import progress

from .constants import DEFAULT_DENSITIES, DEFAULT_OCEAN_AREA, DEFAULT_DASK_CONFIG
from .utils import validate_input_data


class SLCCalculator:
    """
    Calculator for sea level contribution from ice sheet data.
    
    This class implements the methodology from Goelzer et al. (2020) for 
    calculating sea level contribution from ice sheet thickness and bed 
    elevation data.
    
    Parameters
    ----------
    rho_ice : float, optional
        Density of ice in kg/m³
    rho_ocean : float, optional  
        Density of seawater in kg/m³
    rho_water : float, optional
        Density of freshwater in kg/m³
    ocean_area : float, optional
        Surface area of the ocean in m²
    quiet : bool, optional
        Whether to suppress all output and progress bars (default: False)
    areacell : xarray.DataArray, optional
        Pre-calculated grid cell areas in m². If provided, bypasses automatic area calculation
    dask_config : dict, optional
        Dask configuration parameters
        
    References
    ----------
    Goelzer et al. (2020): https://doi.org/10.5194/tc-14-833-2020
    """
    
    def __init__(
        self,
        rho_ice: float = None,
        rho_ocean: float = None, 
        rho_water: float = None,
        ocean_area: float = None,
        quiet: bool = False,
        dask_config: dict = None,
        areacell: DataArray = None,
    ):
        self.rho_ice = rho_ice if rho_ice is not None else DEFAULT_DENSITIES["ice"]
        self.rho_ocean = rho_ocean if rho_ocean is not None else DEFAULT_DENSITIES["ocean"] 
        self.rho_water = rho_water if rho_water is not None else DEFAULT_DENSITIES["water"]
        self.ocean_area = ocean_area if ocean_area is not None else DEFAULT_OCEAN_AREA
        self.quiet = quiet
        self.dask_config = dask_config or DEFAULT_DASK_CONFIG.copy()
        self.areacell = areacell  # Pre-calculated area values
        self._cluster = None
        self._client = None
        
        # Validate parameters
        if self.rho_ice <= 0:                            
            raise ValueError("Ice density must be positive")
        if self.rho_ocean <= 0:
            raise ValueError("Ocean density must be positive")
        if self.rho_water <= 0:
            raise ValueError("Water density must be positive")
        if self.ocean_area <= 0:
            raise ValueError("Ocean area must be positive")
            
        # Always set up dask cluster
        self._setup_dask_cluster()
            
    def _setup_dask_cluster(self):
        """Set up dask cluster for parallel computation with memory limits."""
        try:
            from dask.distributed import get_client
            self._client = get_client()
        except ValueError:
            from dask.distributed import Client, LocalCluster
            self._cluster = LocalCluster(**self.dask_config)
            self._client = Client(self._cluster)
            
    def _cleanup_dask_cluster(self):
        """Clean up dask cluster resources."""
        if self._client is not None:
            self._client.close()
            self._client = None
            
        if self._cluster is not None:
            self._cluster.close()
            self._cluster = None
            
    def __enter__(self):
        """Context manager entry."""
        return self
        
    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit - clean up dask resources."""
        self._cleanup_dask_cluster()
        
    def calculate_slc(
        self, 
        thickness: DataArray, 
        z_base: DataArray,
        grounded_fraction: DataArray = None,
    ) -> DataArray:
        """
        Calculate sea level contribution from ice thickness and bed elevation.
        
        Parameters
        ----------
        thickness : xarray.DataArray
            Ice sheet thickness with dimensions (x, y, time)
        z_base : xarray.DataArray  
            Bed elevation with dimensions (x, y, time)
        grounded_fraction : xarray.DataArray, optional
            Pre-calculated grounded fractions (0=floating, 1=grounded). If provided, 
            bypasses automatic floatation criteria calculation. Values should be between 0 and 1.
            
        Returns
        -------
        xarray.DataArray
            Sea level contribution grid with dimensions (x, y, time)
        """
        # Always validate input data
        validate_input_data(thickness, z_base)
            
        # Fill NaNs in thickness
        thickness = thickness.fillna(0)
        
        # Get grid cell area - use provided areacell or calculate it
        if self.areacell is not None:
            areacell = self.areacell
        else:
            areacell = self._calculate_areacell(thickness)
        
        # Calculate all components lazily (no intermediate compute calls)
        slc_af = self._calculate_volume_above_floatation(thickness, z_base, areacell, grounded_fraction)
        slc_pov = self._calculate_potential_ocean_volume(z_base, areacell)
        slc_den = self._calculate_density_correction(thickness, areacell)
        
        # Sum all components together (still lazy computation)
        slc_total = slc_af + slc_pov + slc_den
        slc_total.name = "slc"
        slc_total.attrs.update({
            "long_name": "Sea level contribution",
            "units": "m",
            "methodology": "Goelzer et al. (2020)",
        })
        
        # Single compute step with progress tracking
        if not self.quiet:
            from dask.distributed import get_client
            get_client()  # Just check if distributed scheduler is available
            # Use distributed progress for distributed scheduler
            slc_total = slc_total.persist()
            progress(slc_total)  # Shows distributed progress bar
            slc_total = slc_total.compute()

        else:
            # Compute without output or progress tracking
            slc_total = slc_total.compute()
        
        return slc_total
        
    def _calculate_areacell(self, thickness: DataArray) -> DataArray:
        """Get area of each grid cell in m² as a DataArray."""
        x = thickness.x
        
        # Handle single pixel case
        if len(x) < 2:
            dx = 1.0  # Default pixel spacing for single pixel
        else:
            dx = float(x[1] - x[0])  # Assumes regularly spaced grid
        
        # Import here to avoid circular imports
        from .utils import scale_factor
        k = scale_factor(thickness, sgn=-1)  # sgn=-1 -> South Polar Stereographic
        
        # Grid cell area (now a DataArray)
        areacell = dx**2 / k**2
        
        return areacell
        
    def _calculate_volume_above_floatation(
        self, 
        thickness: DataArray, 
        z_base: DataArray, 
        areacell: DataArray,
        grounded_fraction: DataArray = None,
    ) -> DataArray:
        """Calculate sea level contribution from volume above floatation."""
        
        # Get grounded fraction - use provided values or calculate from floatation criteria
        if grounded_fraction is not None:
            grounded_frac = grounded_fraction
        else:
            # Calculate grounded fraction from floatation criteria (binary: 0 or 1)
            grounded_frac = (thickness > -z_base * self.rho_ocean / self.rho_ice).astype(float)
        
        # Calculate volume above floatation for all points
        # This includes both grounded and floating areas
        v_af_total = (
            thickness + 
            np.minimum(z_base, 0) * self.rho_ocean / self.rho_ice
        ) * areacell
        
        # Weight by grounded fraction (0 for floating, 1 for grounded, fractional for mixed)
        v_af_grounded = v_af_total * grounded_frac
        
        # Sea level contribution (relative to first time step)
        slc_af = -(v_af_grounded - v_af_grounded.isel(time=0)) * (self.rho_ice / self.rho_ocean) / self.ocean_area
        
        return slc_af
        
    def _calculate_potential_ocean_volume(
        self, 
        z_base: DataArray, 
        areacell: DataArray, 
    ) -> DataArray:
        """Calculate sea level contribution from potential ocean volume."""
        v_pov = np.maximum(-z_base, 0) * areacell
        slc_pov = -(v_pov - v_pov.isel(time=0)) / self.ocean_area
        
        return slc_pov
        
    def _calculate_density_correction(
        self, 
        thickness: DataArray, 
        areacell: DataArray, 
    ) -> DataArray:
        """Calculate density correction for floating ice."""
        v_den = thickness * (
            self.rho_ice / self.rho_water - self.rho_ice / self.rho_ocean
        ) * areacell
        
        slc_den = -(v_den - v_den.isel(time=0)) / self.ocean_area
        
        return slc_den
        
    def calculate_components(
        self, 
        thickness: DataArray, 
        z_base: DataArray,
        grounded_fraction: DataArray = None,
    ) -> Dict[str, DataArray]:
        """
        Calculate individual SLC components separately.
        
        Parameters
        ----------
        thickness : xarray.DataArray
            Ice sheet thickness
        z_base : xarray.DataArray
            Bed elevation
        grounded_fraction : xarray.DataArray, optional
            Pre-calculated grounded fractions (0=floating, 1=grounded). If provided, 
            bypasses automatic floatation criteria calculation. Values should be between 0 and 1.
            
        Returns
        -------
        dict
            Dictionary with 'af', 'pov', 'density', and 'total' components
        """
        # Always validate input data
        validate_input_data(thickness, z_base)
            
        thickness = thickness.fillna(0)
        
        # Get grid cell area - use provided areacell or calculate it
        if self.areacell is not None:
            areacell = self.areacell
        else:
            areacell = self._calculate_areacell(thickness)
        
        components = {
            "af": self._calculate_volume_above_floatation(thickness, z_base, areacell, grounded_fraction),
            "pov": self._calculate_potential_ocean_volume(z_base, areacell), 
            "density": self._calculate_density_correction(thickness, areacell),
        }
        
        components["total"] = sum(components.values())
        components["total"].name = "slc_total"
        
        return components
