"""
Core sea level contribution calculations based on Goelzer et al. (2020).
"""
import numpy as np
import xarray as xr
from pathlib import Path
from typing import Optional
from xarray import DataArray
from dask.distributed import progress

from .config import DENSITIES, OCEAN_AREA, VARNAMES, DASK_CONFIG, CHUNKS
from .utils import validate_input_data


class SLECalculator:
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
        areacell: Optional[DataArray] = None, 
        quiet: bool = False,
        show_memory: bool = False,
    ):
        self.areacell = areacell    # Pre-calculated area values
        self.quiet = quiet          # Suppress output and progress bars
        self.show_memory = show_memory  # Show memory usage during processing

        # Get parameters from config
        self.rho_ice = DENSITIES["ice"]
        self.rho_ocean = DENSITIES["ocean"] 
        self.rho_water = DENSITIES["water"]
        self.ocean_area = OCEAN_AREA
        self.varnames = VARNAMES
        self.dask_config = DASK_CONFIG
        self.chunks = CHUNKS

        # Dask cluster and client
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
            
        # Print dashboard URL for memory monitoring
        if not self.quiet and self._client:
            dashboard_link = self._client.dashboard_link
            if dashboard_link:
                print(f"📊 Dask dashboard available at: {dashboard_link}")
                print("   Use this to monitor memory usage and task progress in real-time")
            
    def close(self):
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
        self.close()
        
    def calculate_sle(
        self, 
        thickness: DataArray, 
        z_base: DataArray,
        grounded_fraction: Optional[DataArray] = None,
        sum: bool = True,
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
        
        # Get grid cell area - use provided areacell or calculate it for an even-gridded South Polar
        # Stereographic projection.
        if self.areacell is not None:
            areacell = self.areacell
        else:
            areacell = self._calculate_areacell(thickness)
        
        # Calculate all components lazily
        sle_af = self._calculate_volume_above_floatation(
            thickness, z_base, areacell, grounded_fraction)
        sle_pov = self._calculate_potential_ocean_volume(z_base, areacell)
        sle_den = self._calculate_density_correction(thickness, areacell)
        
        # Sum all components together (still lazy computation)
        sle = sle_af + sle_pov + sle_den
        sle.name = "sle"
        sle.attrs.update({
            "long_name": "Sea level contribution",
            "units": "m",
            "methodology": "Goelzer et al. (2020)",
        })
        
        # Single compute step with progress tracking
        if not self.quiet:
            # Use distributed progress for distributed scheduler
            sle = sle.persist()
            progress(sle)  # Shows distributed progress bar
            sle = sle.compute()
        else:
            # Compute without output or progress tracking
            sle = sle.compute()
        
        if sum:
            return sle.sum(dim=["x", "y"])  # Sum over spatial dimensions
        return sle

    def process_ensemble(
            self,
            thickness_dir: str|Path,
            z_base_dir: str|Path,
            grounded_fraction_dir: Optional[str|Path] = None,
            basins_file: Optional[str|Path] = None,
    ):
        """
        Apply calculate_sle to an ensemble of ice sheet model runs.

        Parameters
        ----------
        thickness_dir : str|Path
            Directory containing ice sheet thickness netCDF files
        z_base_dir : str|Path
            Directory containing bed elevation netCDF files
        grounded_fraction_dir : Optional[str|Path]
            Directory containing grounded fraction netCDF files for ensemble processing
        basins_file : Optional[str|Path]
            Basin mask netCDF file for regional SLE timeseries

        Returns
        -------
        xarray.DataArray
            Ensemble sea level contribution timeseries with dimensions (run, time[, basin])
        
        """
        # Convert all strings to paths
        thickness_dir = Path(thickness_dir)
        z_base_dir = Path(z_base_dir)
        if grounded_fraction_dir is not None:
            grounded_fraction_dir = Path(grounded_fraction_dir)
        if basins_file is not None:
            basins_file = Path(basins_file)

        thk_files, zb_files, gf_files = self._validate_files(
            thickness_dir, z_base_dir, grounded_fraction_dir
            )

        # load basin mask into memory
        basins = self._load_basins(basins_file) if basins_file else None

        timeseries = []
        for i, (thk_file, zb_file) in enumerate(zip(thk_files, zb_files)):
            gf_file = gf_files[i] if gf_files else None

            # Print progress if not quiet
            if not self.quiet:
                print(f"Processing ensemble run {i+1}/{len(thk_files)}: {thk_file.stem}")
            
            # Show memory usage if requested
            if self.show_memory:
                self._print_memory_usage(f"Before run {i+1}")
            
            thk, zb, gf = self._load_run_data(thk_file, zb_file, gf_file)
            # Calculate sea level contribution
            sle_grid = self.calculate_sle(thk, zb, gf, sum=False)

            # Before summing over spatial dimensions, apply basin mask (if provided)
            if basins is not None:
                ts = sle_grid.groupby(basins).sum(dim=["x", "y"])
            else:
                ts = sle_grid.sum(dim=["x", "y"])
            timeseries.append(ts.compute())
            
            # Show memory usage after processing
            if self.show_memory:
                self._print_memory_usage(f"After run {i+1}")
                print()  # Add spacing

        # Print final status
        if not self.quiet:
            print(f"Completed processing {len(timeseries)} ensemble runs")
            
        # Combine into ensemble with aligned time dimensions
        run_labels = range(1, len(timeseries) + 1)
        ensemble = self._align_and_concat_timeseries(timeseries, run_labels)
        
        return ensemble
    
    def _align_and_concat_timeseries(self, timeseries, run_labels):
        """
        Align time dimensions and concatenate timeseries with different time lengths.
        
        This method creates a union of all time coordinates and reindexes each
        timeseries to this common time grid, filling missing values with NaN.
        
        Parameters
        ----------
        timeseries_list : list of xarray.DataArray
            List of timeseries DataArrays with potentially different time dimensions
        run_labels : range or list
            Labels for the run dimension
            
        Returns
        -------
        xarray.DataArray
            Concatenated timeseries with aligned time dimensions
        """
            
        # Get all unique time coordinates
        times = np.array([])
        for ts in timeseries:
            times = np.append(times, ts.time.values)
        unique_times = sorted(np.unique(times))
        
        # Reindex each timeseries to the union time grid
        aligned_timeseries = []
        for ts in timeseries:
            # Reindex to union time coordinates, filling missing values with NaN
            aligned_ts = ts.reindex(time=unique_times, fill_value=np.nan)
            aligned_timeseries.append(aligned_ts)
        
        # Now concatenate along run dimension
        ensemble = xr.concat(aligned_timeseries, dim="run")
        ensemble = ensemble.assign_coords(run=run_labels)
        
        return ensemble

    def _load_run_data(
            self,
            thickness_file: str|Path,
            z_base_file: str|Path,
            grounded_fraction_file: Optional[str|Path] = None,
    ):
        """
        Loads thickness, bed elevation, and optionally grounded fraction data for a single run,
        using specified variable names and chunking from config.
        """
        
        # Load data
        thickness_ds = xr.open_dataset(thickness_file, engine="netcdf4")
        z_base_ds = xr.open_dataset(z_base_file, engine="netcdf4")

        thickness = thickness_ds[self.varnames["thickness"]]
        z_base = z_base_ds[self.varnames["bed_elevation"]]

        # Chunk data for parallel processing
        thickness = thickness.chunk(self.chunks)
        z_base = z_base.chunk(self.chunks)

        if grounded_fraction_file:
            grounded_fraction_ds = xr.open_dataset(grounded_fraction_file, engine="netcdf4")
            grounded_fraction = grounded_fraction_ds[self.varnames["grounded_fraction"]]
            grounded_fraction = grounded_fraction.chunk(self.chunks)
            return thickness, z_base, grounded_fraction
        
        return thickness, z_base, None

    def _load_basins(self, mask_file: Path) -> DataArray:
        """Load basin mask for regional analysis."""
        with xr.open_dataset(mask_file) as ds:
            basins = ds[self.varnames["basin"]]
            return basins.load()

    def _validate_files(
        self,
        thickness_dir: Path,
        z_base_dir: Path,
        grounded_fraction_dir: Optional[Path] = None,
    ):

        # Validate directories exist
        if not thickness_dir.is_dir():
            raise ValueError(f"Thickness directory does not exist: {thickness_dir}")
        if not z_base_dir.is_dir():
            raise ValueError(f"Bed elevation directory does not exist: {z_base_dir}")
        if grounded_fraction_dir and not grounded_fraction_dir.is_dir():
            raise ValueError(f"Grounded fraction directory does not exist: {grounded_fraction_dir}")
        
        # Get all files in directories
        thickness_files = sorted(thickness_dir.glob("*.nc"))
        z_base_files = sorted(z_base_dir.glob("*.nc"))
        grounded_fraction_files = []
        if grounded_fraction_dir:
            grounded_fraction_files = sorted(grounded_fraction_dir.glob("*.nc"))

        # Validate file counts match
        if len(thickness_files) != len(z_base_files):
            raise ValueError(
                f"Mismatched number of files: {len(thickness_files)} thickness, "
                f"{len(z_base_files)} z_base files"
        )
        if grounded_fraction_files and len(grounded_fraction_files) != len(thickness_files):
            raise ValueError(
                f"Mismatched number of files: {len(thickness_files)} thickness, "
                f"{len(grounded_fraction_files)} grounded fraction files"
                )
        
        return thickness_files, z_base_files, grounded_fraction_files

    def _calculate_areacell(self, thickness: DataArray) -> DataArray:
        """Get area of each grid cell in m² as a DataArray. Assumes even-gridded data and a 
        South Polar Stereographic projection."""
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
        grounded_fraction: Optional[DataArray] = None,
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
        v_af = (
            thickness + 
            np.minimum(z_base, 0) * self.rho_ocean / self.rho_ice
        ) * areacell * grounded_frac
        
        # Sea level contribution (relative to first time step)
        sle_af = -(v_af - v_af.isel(time=0)) * (self.rho_ice / self.rho_ocean) / self.ocean_area
        
        return sle_af

    def _calculate_potential_ocean_volume(
        self, 
        z_base: DataArray, 
        areacell: DataArray, 
    ) -> DataArray:
        """Calculate sea level contribution from potential ocean volume."""
        v_pov = (-z_base).clip(min=0) * areacell
        sle_pov = -(v_pov - v_pov.isel(time=0)) / self.ocean_area
        
        return sle_pov
        
    def _calculate_density_correction(
        self, 
        thickness: DataArray, 
        areacell: DataArray, 
    ) -> DataArray:
        """Calculate density correction for floating ice."""
        v_den = thickness * (
            self.rho_ice / self.rho_water - self.rho_ice / self.rho_ocean
        ) * areacell
        
        sle_den = -(v_den - v_den.isel(time=0)) / self.ocean_area
        
        return sle_den
        
    def _print_memory_usage(self, context: str = ""):
        """Print current memory usage statistics."""
        try:
            import psutil
            
            # Get process memory info
            process = psutil.Process()
            memory_info = process.memory_info()
            memory_mb = memory_info.rss / 1024 / 1024
            
            # Get system memory info
            sys_memory = psutil.virtual_memory()
            sys_total_gb = sys_memory.total / 1024 / 1024 / 1024
            sys_used_gb = sys_memory.used / 1024 / 1024 / 1024
            sys_percent = sys_memory.percent
            
            print(f"💾 Memory Usage {context}:")
            print(f"   Process: {memory_mb:.1f} MB")
            print(f"   System: {sys_used_gb:.1f}/{sys_total_gb:.1f} GB ({sys_percent:.1f}%)")
            
            # Get dask cluster memory if available
            if self._client:
                try:
                    # Get worker info
                    worker_info = self._client.scheduler_info()['workers']
                    if worker_info:
                        total_dask_memory = 0
                        for worker_id, worker_data in worker_info.items():
                            worker_memory = worker_data.get('memory_limit', 0)
                            total_dask_memory += worker_memory
                        
                        if total_dask_memory > 0:
                            dask_memory_gb = total_dask_memory / 1024 / 1024 / 1024
                            print(f"   Dask workers: {dask_memory_gb:.1f} GB limit")
                except Exception:
                    pass  # Silently ignore dask memory errors
                    
        except ImportError:
            print("💾 Memory monitoring requires psutil: pip install psutil")
        except Exception as e:
            print(f"💾 Memory monitoring error: {e}")