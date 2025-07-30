"""
Ensemble processing for multiple ice sheet model runs.
"""

from typing import Optional
from pathlib import Path
import numpy as np
import xarray as xr
from xarray import DataArray
from dask.distributed import Client, LocalCluster, get_client

from .core import SLCCalculator
from .utils import prepare_chunked_data
from .constants import DEFAULT_DASK_CONFIG


class EnsembleProcessor:
    """
    Process ensembles of ice sheet model runs to calculate sea level contributions.
    
    This class handles the orchestration of SLC calculations across multiple
    model runs, with support for parallel computation using dask.
    
    Parameters
    ----------
    calculator : SLCCalculator, optional
        SLC calculator instance. If None, creates default calculator
    parallel : bool, optional
        Whether to use parallel computation with dask
    dask_config : dict, optional
        Dask configuration parameters
    show_progress : bool, optional
        Whether to show progress bar during processing (default: True)
    """
    
    def __init__(
        self,
        calculator: Optional[SLCCalculator] = None,
        parallel: bool = True,
        dask_config: dict = None,
        show_progress: bool = True,
    ):
        self.calculator = calculator or SLCCalculator()
        self.parallel = parallel
        self.dask_config = dask_config or DEFAULT_DASK_CONFIG.copy()
        self.show_progress = show_progress
        self._cluster = None
        self._client = None
        
    def __enter__(self):
        """Context manager entry - set up dask cluster if needed."""
        if self.parallel:
            self._setup_dask_cluster()
        return self
        
    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit - clean up dask resources."""
        self._cleanup_dask_cluster()
        
    def process_ensemble(
        self,
        thickness_dir: Path,
        z_base_dir: Path,
        mask_file: Optional[Path] = None,
        chunks: dict = None,
    ) -> DataArray:
        """
        Process an ensemble of model runs to calculate SLC timeseries.
        
        Parameters
        ----------
        thickness_dir : Path
            Directory containing thickness netCDF files
        z_base_dir : Path  
            Directory containing bed elevation netCDF files
        mask_file : Path, optional
            Basin mask file for regional analysis
        chunks : dict, optional
            Custom chunk sizes for parallel computation
            
        Returns
        -------
        xarray.DataArray
            Sea level contribution timeseries with run dimension
        """
        # Get file paths
        thickness_files = sorted(Path(thickness_dir).glob("*.nc"))
        z_base_files = sorted(Path(z_base_dir).glob("*.nc"))
        
        if len(thickness_files) != len(z_base_files):
            raise ValueError(
                f"Mismatched number of files: {len(thickness_files)} thickness, "
                f"{len(z_base_files)} z_base files"
            )
            
        # Load mask if provided
        mask = None
        if mask_file:
            mask = self._load_mask(mask_file)
            
        # Process each run
        timeseries = []
        
        for i, (thk_file, zb_file) in enumerate(zip(thickness_files, z_base_files), 1):
            # Print progress if enabled
            if self.show_progress:
                print(f"Processing ensemble run {i}/{len(thickness_files)}: {thk_file.stem}")
            
            # Load and prepare data
            thickness, z_base = self._load_run_data(thk_file, zb_file, chunks=chunks)
            
            # Calculate SLC
            slc_grid = self.calculator.calculate_slc(thickness, z_base)
            
            # Aggregate by mask or globally
            if mask is not None:
                timeseries_run = self._timeseries_by_basin(slc_grid, mask)
            else:
                timeseries_run = slc_grid.sum(dim=["x", "y"])
            
            timeseries.append(timeseries_run.compute())

        
        # Print final status
        if self.show_progress:
            print(f"Completed processing {len(timeseries)} ensemble runs")
            
        # Combine into ensemble
        run_labels = range(1, len(timeseries) + 1)
        ensemble = xr.concat(timeseries, dim="run")
        ensemble = ensemble.assign_coords(run=run_labels)
        
        return ensemble
        
    def _setup_dask_cluster(self):
        """Set up dask cluster for parallel computation."""
        try:
            self._client = get_client()
        except ValueError:
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
            
    def _load_run_data(
        self, 
        thickness_file: Path, 
        z_base_file: Path,
        chunks: dict = None,
    ) -> tuple[DataArray, DataArray]:
        """Load and prepare data for a single model run."""
        # Load datasets
        thk_ds = xr.open_dataset(thickness_file, engine="netcdf4")
        zb_ds = xr.open_dataset(z_base_file, engine="netcdf4")
        
        # Extract variables first (assuming standard naming after forcing convention)
        thickness = thk_ds.thickness if "thickness" in thk_ds else thk_ds[list(thk_ds.data_vars)[0]]
        z_base = zb_ds.Z_base if "Z_base" in zb_ds else zb_ds[list(zb_ds.data_vars)[0]]
        
        # Apply chunking if parallel processing is enabled
        if self.parallel:
            thickness = prepare_chunked_data(thickness, chunks, self.parallel)
            z_base = prepare_chunked_data(z_base, chunks, self.parallel)
        
        return thickness, z_base
        
    def _load_mask(self, mask_file: Path) -> DataArray:
        """Load basin mask for regional analysis."""
        with xr.open_dataset(mask_file) as ds:
            # Assume mask variable is named 'basin' or take first variable
            mask = ds.basin if "basin" in ds else ds[list(ds.data_vars)[0]]
            return mask.load()  # Load into memory
            
    def _timeseries_by_basin(self, slc_grid: DataArray, mask: DataArray) -> DataArray:
        """Calculate timeseries by basin using mask."""
        # Use xarray's built-in reindexing to handle coordinate differences
        # This is more robust than strict alignment checking
        mask_reindexed = mask.reindex_like(slc_grid.isel(time=0), method="nearest")
        
        # Get unique basin IDs
        basin_ids = np.unique(mask_reindexed.values[~np.isnan(mask_reindexed.values)])
        basin_ids = basin_ids[basin_ids != 0]  # Remove 0 (typically ocean/no-data)
        
        # Calculate timeseries for each basin
        basin_timeseries = []
        for basin_id in basin_ids:
            basin_mask = (mask_reindexed == basin_id)
            basin_ts = slc_grid.where(basin_mask).sum(dim=["x", "y"])
            basin_timeseries.append(basin_ts)
            
        # Combine into single DataArray
        result = xr.concat(basin_timeseries, dim="basin")
        result = result.assign_coords(basin=basin_ids)
        
        return result
        
    def save_results(self, data: DataArray, output_file: Path, overwrite: bool = False):
        """
        Save results to netCDF file.
        
        Parameters
        ----------
        data : xarray.DataArray
            Data to save
        output_file : Path
            Output file path
        overwrite : bool, optional
            Whether to overwrite existing files
        """
        output_file = Path(output_file)
        
        if output_file.suffix != ".nc":
            raise ValueError("Output file must have .nc extension")
            
        if output_file.exists() and not overwrite:
            raise FileExistsError(
                f"{output_file.name} already exists. Use overwrite=True to overwrite."
            )
            
        if overwrite and output_file.exists():
            output_file.unlink()
            
        # Convert to dataset and save
        ds = data.to_dataset(name="slc")
        ds.attrs.update({
            "title": "Sea level contribution from ice sheet model ensemble",
            "methodology": "Goelzer et al. (2020)",
            "software": "py-sle",
        })
        
        ds.to_netcdf(output_file)
