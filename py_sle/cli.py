"""
Command-line interface for py-sle.
"""

import argparse
from pathlib import Path
import sys

from .ensemble import EnsembleProcessor
from .core import SLCCalculator


def create_parser() -> argparse.ArgumentParser:
    """Create command-line argument parser."""
    parser = argparse.ArgumentParser(
        description="Calculate sea level contribution from ice sheet model ensemble",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Basic usage
  goelzer-slc thickness/ z_base/ output.nc
  
  # With basin mask
  goelzer-slc thickness/ z_base/ output.nc --mask basins.nc
  
  # With custom area file
  goelzer-slc thickness/ z_base/ output.nc --areacell areas.nc
  
  # Custom parameters
  goelzer-slc thickness/ z_base/ output.nc --rho-ice 917 --rho-ocean 1025
        """,
    )
    
    # Required arguments
    parser.add_argument(
        "thickness_dir",
        type=str,
        help="Directory containing thickness netCDF files"
    )
    parser.add_argument(
        "z_base_dir", 
        type=str,
        help="Directory containing bed elevation netCDF files"
    )
    parser.add_argument(
        "output_file",
        type=str, 
        help="Output netCDF file path"
    )
    
    # Optional arguments
    parser.add_argument(
        "--mask",
        type=str,
        help="Basin mask netCDF file for regional analysis"
    )
    parser.add_argument(
        "--areacell",
        type=str,
        help="Grid cell area netCDF file (bypasses automatic area calculation)"
    )
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="Overwrite output file if it exists"
    )
    parser.add_argument(
        "-q", "--quiet",
        action="store_true",
        help="Suppress all output and progress bars"
    )
    
    # Physical parameters
    params_group = parser.add_argument_group("Physical parameters")
    params_group.add_argument(
        "--rho-ice",
        type=float,
        default=918.0,
        help="Ice density in kg/m³ (default: 918.0)"
    )
    params_group.add_argument(
        "--rho-ocean", 
        type=float,
        default=1028.0,
        help="Ocean water density in kg/m³ (default: 1028.0)"
    )
    params_group.add_argument(
        "--rho-water",
        type=float, 
        default=1000.0,
        help="Fresh water density in kg/m³ (default: 1000.0)"
    )
    params_group.add_argument(
        "--ocean-area",
        type=float,
        default=3.625e14,
        help="Ocean surface area in m² (default: 3.625e14)"
    )
    
    # Dask configuration
    dask_group = parser.add_argument_group("Dask configuration")
    dask_group.add_argument(
        "--workers",
        type=int,
        default=4,
        help="Number of dask workers (default: 4)"
    )
    dask_group.add_argument(
        "--threads-per-worker",
        type=int,
        default=2, 
        help="Threads per worker (default: 2)"
    )
    dask_group.add_argument(
        "--memory-limit",
        type=str,
        default="4GB",
        help="Memory limit per worker (default: 4GB)"
    )
    
    return parser


def main(args=None):
    """Main CLI entry point."""
    parser = create_parser()
    args = parser.parse_args(args)
    
    # Validate paths
    thickness_dir = Path(args.thickness_dir)
    z_base_dir = Path(args.z_base_dir)
    output_file = Path(args.output_file)
    mask_file = Path(args.mask) if args.mask else None
    areacell_file = Path(args.areacell) if args.areacell else None
    
    if not thickness_dir.exists():
        print(f"Error: Thickness directory not found: {thickness_dir}")
        sys.exit(1)
        
    if not z_base_dir.exists():
        print(f"Error: Z_base directory not found: {z_base_dir}")
        sys.exit(1)
        
    if mask_file and not mask_file.exists():
        print(f"Error: Mask file not found: {mask_file}")
        sys.exit(1)
        
    if areacell_file and not areacell_file.exists():
        print(f"Error: Areacell file not found: {areacell_file}")
        sys.exit(1)
        
    if output_file.suffix != ".nc":
        print("Error: Output file must have .nc extension")
        sys.exit(1)
    
    # Load areacell if provided
    areacell = None
    if areacell_file:
        try:
            from .utils import load_areacell
            areacell = load_areacell(str(areacell_file))
        except ValueError as e:
            print(f"Error loading areacell file: {e}")
            sys.exit(1)
    
    # Create calculator with custom parameters
    calculator = SLCCalculator(
        rho_ice=args.rho_ice,
        rho_ocean=args.rho_ocean,
        rho_water=args.rho_water,
        ocean_area=args.ocean_area,
        quiet=args.quiet,
        areacell=areacell,
    )
    
    # Configure dask
    dask_config = {
        "n_workers": args.workers,
        "threads_per_worker": args.threads_per_worker,
        "memory_limit": args.memory_limit,
        "dashboard_address": None,
    }
    
    # Process ensemble
    try:
        with EnsembleProcessor(
            calculator=calculator,
            dask_config=dask_config,
            quiet=args.quiet,
        ) as processor:
            
            if not args.quiet:
                print("Processing ensemble...")
                print(f"Thickness dir: {thickness_dir}")
                print(f"Z_base dir: {z_base_dir}")
                if mask_file:
                    print(f"Basin mask: {mask_file}")
                if areacell_file:
                    print(f"Areacell file: {areacell_file}")
                print(f"Output: {output_file}")
                print(f"Dask config: {args.workers} workers × {args.threads_per_worker} threads")
            
            # Calculate SLC
            results = processor.process_ensemble(
                thickness_dir=thickness_dir,
                z_base_dir=z_base_dir,
                mask_file=mask_file,
            )
            
            # Save results
            processor.save_results(
                data=results,
                output_file=output_file,
                overwrite=args.overwrite,
            )
            
            if not args.quiet:
                print(f"✓ Results saved to {output_file}")
                print(f"  Ensemble size: {results.sizes['run']} runs")
                print(f"  Time steps: {results.sizes['time']} steps")
                if 'basin' in results.dims:
                    print(f"  Basins: {results.sizes['basin']} basins")
                
    except Exception as e:
        print(f"Error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
