"""
Command-line interface for slepy.
"""

import sys
import argparse
from pathlib import Path
from xarray import DataArray

from .core import SLECalculator


def create_parser() -> argparse.ArgumentParser:
    """Create command-line argument parser."""
    parser = argparse.ArgumentParser(
        description="Calculate sea level contribution from ice sheet model ensemble",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Basic usage
  slepy thickness/ z_base/ output.nc
  
  # With basin mask
  slepy thickness/ z_base/ output.nc --mask basins.nc
  
  # With custom area file
  slepy thickness/ z_base/ output.nc --areacell areas.nc
  
  # With grounded fraction directory
  slepy thickness/ z_base/ output.nc --grounded-fraction-dir grounded_fraction/
        """,
    )
    
    # Required arguments
    parser.add_argument(
        "thickness_dir",
        type=Path,
        help="Directory containing thickness netCDF files"
    )
    parser.add_argument(
        "z_base_dir", 
        type=Path,
        help="Directory containing bed elevation netCDF files"
    )
    parser.add_argument(
        "output_file",
        type=Path, 
        help="Output netCDF file path"
    )
    
    # Optional arguments
    parser.add_argument(
        "-M", "--mask",
        type=Path,
        help="Basin mask netCDF file for regional analysis"
    )
    parser.add_argument(
        "-A", "--areacell",
        type=Path,
        help="Grid cell area netCDF file (bypasses automatic area calculation)"
    )
    parser.add_argument(
        "-G", "--grounded-fraction-dir",
        type=Path,
        help="Directory containing grounded fraction netCDF files for ensemble processing"
    )
    parser.add_argument(
        "-o", "--overwrite",
        action="store_true",
        help="Overwrite output file if it exists"
    )
    parser.add_argument(
        "-q", "--quiet",
        action="store_true",
        help="Suppress all output and progress bars"
    )
    parser.add_argument(
        "--show-memory",
        action="store_true",
        help="Show memory usage during processing (requires psutil)"
    )
    
    return parser

def validate_arg_paths(args) -> None:
    """Validate that provided paths exist and are correct."""
    if not args.thickness_dir.exists():
        raise FileNotFoundError(f"Thickness directory not found: {args.thickness_dir}")
    
    if not args.z_base_dir.exists():
        raise FileNotFoundError(f"Z_base directory not found: {args.z_base_dir}")
    
    if args.output_file.suffix != ".nc":
        raise ValueError("Output file must have .nc extension")
    
    if args.output_file.exists() and not args.overwrite:
        raise FileExistsError(f"{args.output_file.name} already exists. Use --overwrite to overwrite.")
    
    if args.mask and not args.mask.exists():
        raise FileNotFoundError(f"Mask file not found: {args.mask}")
    
    if args.areacell and not args.areacell.exists():
        raise FileNotFoundError(f"Areacell file not found: {args.areacell}")
    
    if args.grounded_fraction_dir and not args.grounded_fraction_dir.exists():
        raise FileNotFoundError(f"Grounded fraction directory not found: {args.grounded_fraction_dir}")
 

def save_results(data: DataArray, output_file: Path, overwrite: bool = False) -> None:
    """
    Save results to netCDF file.
    
    Parameters
    ----------
    data : xarray.DataArray
        Data to save
    output_file : Path or str
        Output file path
    overwrite : bool, optional
        Whether to overwrite existing files
    """
    
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
        "title": "Sea level contribution",
        "methodology": "Goelzer et al. (2020)",
        "software": "slepy",
    })
    
    ds.to_netcdf(output_file)

def main(args=None):
    """Main CLI entry point."""
    parser = create_parser()
    args = parser.parse_args(args)
    validate_arg_paths(args)
    
    # Load areacell if provided
    areacell = None
    if args.areacell:
        from .utils import load_areacell
        areacell = load_areacell(args.areacell)

    # Initialize calculator
    calc = SLECalculator(areacell=areacell, quiet=args.quiet, show_memory=args.show_memory)

    # Print inputs summary   
    if not args.quiet:
        print("Processing ensemble...")
        print(f"Thickness dir: {args.thickness_dir}")
        print(f"Z_base dir: {args.z_base_dir}")
        if args.mask:
            print(f"Basin mask: {args.mask}")
        if args.areacell:
            print(f"Areacell file: {args.areacell}")
        if args.grounded_fraction_dir:
            print(f"Grounded fraction dir: {args.grounded_fraction_dir}")
        print(f"Output: {args.output_file}")

    # Calculate SLE 
    sle = calc.process_ensemble(
        thickness_dir=args.thickness_dir,
        z_base_dir=args.z_base_dir,
        basins_file=args.mask,
        grounded_fraction_dir=args.grounded_fraction_dir,
    )
    calc.close() # clean up memory

    # Save to file
    save_results(sle, args.output_file, overwrite=args.overwrite)
    
    # Print results summary
    if not args.quiet:
        print(f"✓ Results saved to {args.output_file}")
        print(f"  Ensemble size: {sle.sizes['run']} runs")
        if 'basin' in sle.dims:
            print(f"  Basins: {sle.sizes['basin']} basins")
        


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"Error: {e}")
        sys.exit(1)
