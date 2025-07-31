"""
Ensemble processing for multiple ice sheet model runs.
"""

import numpy as np
import xarray as xr
from pathlib import Path
from typing import Optional
from xarray import DataArray
from dask.distributed import Client, LocalCluster, get_client

from .core import SLECalculator
from .utils import prepare_chunked_data
from .defaults import DEFAULT_DASK_CONFIG, DEFAULT_VARNAMES


class EnsembleProcessor:
    """
    Process ensembles of ice sheet model runs to calculate sea level contributions.
    
    This class handles the orchestration of SLE calculations across multiple
    model runs using parallel computation with dask.
    
    Parameters
    ----------
    calculator : SLECalculator, optional
        SLE calculator instance. If None, creates default calculator
    dask_config : dict, optional
        Dask configuration parameters
    quiet : bool, optional
        Whether to suppress all output and progress bars (default: False)
    varnames : dict, optional
        Partial variable names dictionary. Only keys that need to be overridden from
        defaults need to be specified. Keys should be 'thickness', 'bed_elevation', 
        'grounded_fraction', 'basin', 'time'. If None, uses DEFAULT_VARNAMES entirely.
    """
    
    def __init__(
        self,
        calculator: Optional[SLECalculator] = None,
        dask_config: dict = None,
        quiet: bool = False,
        varnames: dict = None,
    ):
        self.calculator = calculator or SLECalculator()
        self.dask_config = dask_config or DEFAULT_DASK_CONFIG.copy()
        self.quiet = quiet
        
        # Merge partial varnames with defaults
        self.varnames = DEFAULT_VARNAMES.copy()
        if varnames:
            self.varnames.update(varnames)
            
        self._cluster = None
        self._client = None
        
    def __enter__(self):
        """Context manager entry - set up dask cluster."""
        self._setup_dask_cluster()
        return self
        
    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit - clean up dask resources."""
        self._cleanup_dask_cluster()
        
    def _find_variable(self, dataset: xr.Dataset, var_type: str) -> DataArray:
        """
        Find a variable in a dataset using flexible naming conventions.
        
        Parameters
        ----------
        dataset : xarray.Dataset
            Dataset to search for variable
        var_type : str
            Type of variable to find (e.g., 'thickness', 'bed_elevation', 'grounded_fraction')
            
        Returns
        -------
        xarray.DataArray
            The found variable
            
        Raises
        ------
        ValueError
            If variable cannot be found
        """
        if var_type not in self.varnames:
            raise ValueError(f"Unknown variable type: {var_type}")
        
        var_name = self.varnames[var_type]
        
        # Try the specified name
        if var_name in dataset:
            return dataset[var_name]
        
        # If no match and it's the only data variable, use it
        data_vars = list(dataset.data_vars)
        if len(data_vars) == 1:
            return dataset[data_vars[0]]
        
        # Otherwise, raise an error with helpful message
        available_vars = list(dataset.data_vars)
        raise ValueError(
            f"Could not find {var_type} variable '{var_name}' in dataset. "
            f"Available variables: {available_vars}. "
            f"Consider passing a custom varnames dictionary to EnsembleProcessor."
        )
        
    def process_ensemble(
        self,
        thickness_dir: Path,
        z_base_dir: Path,
        grounded_fraction_dir: Optional[Path] = None,
        mask_file: Optional[Path] = None,
        chunks: dict = None,
    ) -> DataArray:
        """
        Process an ensemble of model runs to calculate SLE timeseries.
        
        Parameters
        ----------
        thickness_dir : Path
            Directory containing thickness netCDF files
        z_base_dir : Path  
            Directory containing bed elevation netCDF files
        grounded_fraction_dir : Path, optional
            Directory containing grounded fraction netCDF files
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
        grounded_fraction_files = []
        
        if grounded_fraction_dir:
            grounded_fraction_files = sorted(Path(grounded_fraction_dir).glob("*.nc"))
            
        # Validate file counts
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
            
        # Load mask if provided
        mask = None
        if mask_file:
            mask = self._load_mask(mask_file)
            
        # Process each run
        timeseries = []
        
        for i, (thk_file, zb_file) in enumerate(zip(thickness_files, z_base_files), 1):
            # Get corresponding grounded fraction file if available
            gf_file = grounded_fraction_files[i-1] if grounded_fraction_files else None
            
            # Print progress if not quiet
            if not self.quiet:
                print(f"Processing ensemble run {i}/{len(thickness_files)}: {thk_file.stem}")
            
            # Load and prepare data
            if gf_file:
                thickness, z_base, grounded_fraction = self._load_run_data(thk_file, zb_file, gf_file, chunks=chunks)
            else:
                thickness, z_base = self._load_run_data(thk_file, zb_file, chunks=chunks)
                grounded_fraction = None
            
            # Calculate SLE
            sle_grid = self.calculator.calculate_sle(thickness, z_base, grounded_fraction=grounded_fraction)
            
            # Aggregate by mask or globally
            if mask is not None:
                timeseries_run = self._timeseries_by_basin(sle_grid, mask)
            else:
                timeseries_run = sle_grid.sum(dim=["x", "y"])
            
            timeseries.append(timeseries_run.compute())

        
        # Print final status
        if not self.quiet:
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
        grounded_fraction_file: Optional[Path] = None,
        chunks: dict = None,
    ):
        """Load and prepare data for a single model run."""
        # Load datasets
        thk_ds = xr.open_dataset(thickness_file, engine="netcdf4")
        zb_ds = xr.open_dataset(z_base_file, engine="netcdf4")
        
        # Extract variables using flexible naming
        thickness = self._find_variable(thk_ds, "thickness")
        z_base = self._find_variable(zb_ds, "bed_elevation")
        
        # Apply chunking for parallel processing
        thickness = prepare_chunked_data(thickness, chunks, True)
        z_base = prepare_chunked_data(z_base, chunks, True)
        
        # Load grounded fraction if provided
        if grounded_fraction_file:
            gf_ds = xr.open_dataset(grounded_fraction_file, engine="netcdf4")
            grounded_fraction = self._find_variable(gf_ds, "grounded_fraction")
            
            # Apply chunking for parallel processing
            grounded_fraction = prepare_chunked_data(grounded_fraction, chunks, True)
            
            return thickness, z_base, grounded_fraction
        
        return thickness, z_base
        
    def _load_mask(self, mask_file: Path) -> DataArray:
        """Load basin mask for regional analysis."""
        with xr.open_dataset(mask_file) as ds:
            mask = self._find_variable(ds, "basin")
            return mask.load()  # Load into memory
            
    def _timeseries_by_basin(self, sle_grid: DataArray, mask: DataArray) -> DataArray:
        """Calculate timeseries by basin using mask."""
        # Use xarray's built-in reindexing to handle coordinate differences
        # This is more robust than strict alignment checking
        mask_reindexed = mask.reindex_like(sle_grid.isel(time=0), method="nearest")
        
        # Get unique basin IDs
        basin_ids = np.unique(mask_reindexed.values[~np.isnan(mask_reindexed.values)])
        basin_ids = basin_ids[basin_ids != 0]  # Remove 0 (typically ocean/no-data)
        
        # Calculate timeseries for each basin
        basin_timeseries = []
        for basin_id in basin_ids:
            basin_mask = (mask_reindexed == basin_id)
            basin_ts = sle_grid.where(basin_mask).sum(dim=["x", "y"])
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
        ds = data.to_dataset(name="sle")
        ds.attrs.update({
            "title": "Sea level contribution from ice sheet model ensemble",
            "methodology": "Goelzer et al. (2020)",
            "software": "slepy",
        })
        
        ds.to_netcdf(output_file)
