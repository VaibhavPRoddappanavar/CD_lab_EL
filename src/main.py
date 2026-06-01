"""
Dead Feature Detector - Main Entry Point

Orchestrates the full pipeline:
  1. Scout CMake flags from build system
  2. Generate configuration matrix (Delta-Sampling)
  3. Build and run each configuration with LLVM instrumentation
  4. Analyze per-configuration coverage independently
  5. Correlate with source-level preprocessor guards
  6. Generate dead-feature report with confidence scores
"""
import os
import sys
import shutil
import time
import subprocess

# Add src directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from scout import scout_flags, filter_flags, extract_source_guards
from orchestrator import generate_matrix, matrix_summary
from builder import build_and_run
from analyzer import (
    analyze_per_config_coverage,
    find_dead_features,
    generate_report,
)


def subprocess_run(args, cwd):
    """Run a subprocess with error handling."""
    subprocess.run(args, cwd=cwd, check=True, capture_output=True)


def main():
    start_time = time.time()

    # Configuration - can be overridden via environment variables
    source_dir = os.environ.get(
        'DFD_SOURCE_DIR',
        os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'testbed'))
    )
    build_root = os.environ.get(
        'DFD_BUILD_ROOT',
        os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'build_matrix'))
    )
    binary_name = os.environ.get('DFD_BINARY_NAME', 'testbed')

    print("=" * 70)
    print("   DEAD FEATURE DETECTOR FOR C/C++ CODEBASES")
    print("=" * 70)
    print(f"  Source directory: {source_dir}")
    print(f"  Build root:      {build_root}")
    print(f"  Binary name:     {binary_name}")
    print()

    # Validate source directory
    if not os.path.isdir(source_dir):
        print(f"ERROR: Source directory not found: {source_dir}")
        sys.exit(1)

    # Check for required tools
    for tool in ['clang++', 'llvm-profdata', 'llvm-cov', 'cmake']:
        try:
            subprocess.run([tool, '--version'], capture_output=True, check=True)
        except (subprocess.CalledProcessError, FileNotFoundError):
            print(f"ERROR: Required tool '{tool}' not found in PATH.")
            sys.exit(1)

    # Clean and create build root
    if os.path.exists(build_root):
        shutil.rmtree(build_root)
    os.makedirs(build_root)

    # --- Step 1: Scout Flags ---
    print("=" * 70)
    print("  STEP 1: Scouting CMake Feature Flags")
    print("=" * 70)

    # Create a temporary build directory for flag discovery
    initial_build = os.path.join(build_root, "scout_build")
    os.makedirs(initial_build)
    try:
        subprocess_run(['cmake', source_dir], initial_build)
    except subprocess.CalledProcessError as e:
        print(f"ERROR: Failed to configure CMake project: {e}")
        sys.exit(1)

    raw_flags = scout_flags(initial_build)
    features = filter_flags(raw_flags)

    if not features:
        print("  WARNING: No feature flags discovered. The project may not use")
        print("  CMake options matching known patterns (FEATURE_, ENABLE_, etc.).")
        print("  Raw flags found:", list(raw_flags.keys())[:10])
        sys.exit(1)

    print(f"  Discovered {len(features)} feature flags:")
    for k, v in sorted(features.items()):
        print(f"    {k}: {v}")

    # --- Step 2: Generate Matrix ---
    print(f"\n{'=' * 70}")
    print("  STEP 2: Generating Build Configuration Matrix")
    print("=" * 70)

    matrix = generate_matrix(features)
    flag_names = list(features.keys())
    print(f"  Generated {len(matrix)} configurations:")
    print(matrix_summary(matrix, flag_names))

    # --- Step 3: Build and Run ---
    print(f"\n{'=' * 70}")
    print("  STEP 3: Building and Running Instrumented Configurations")
    print("=" * 70)

    success_count = 0
    config_flags = {}  # Map config_id -> config dict for later reference
    for i, config in enumerate(matrix):
        config_flags[i] = config
        try:
            success, build_dir = build_and_run(
                config, source_dir, build_root, i, binary_name
            )
            if success:
                success_count += 1
        except Exception as e:
            print(f"  Config {i} failed with exception: {e}")

    print(f"\n  Completed {success_count}/{len(matrix)} builds successfully.")

    if success_count == 0:
        print("  ERROR: No builds succeeded. Cannot proceed with analysis.")
        sys.exit(1)

    # --- Step 4: Analyze Coverage ---
    print(f"\n{'=' * 70}")
    print("  STEP 4: Analyzing Per-Configuration Coverage")
    print("=" * 70)

    per_config_cov = analyze_per_config_coverage(build_root, binary_name)

    if not per_config_cov:
        print("  ERROR: No coverage data could be analyzed.")
        sys.exit(1)

    # --- Step 5: Extract Source Guards ---
    print(f"\n{'=' * 70}")
    print("  STEP 5: Extracting Preprocessor Guards from Source")
    print("=" * 70)

    import glob as _glob
    source_files = (
        _glob.glob(os.path.join(source_dir, "*.cpp")) +
        _glob.glob(os.path.join(source_dir, "*.c")) +
        _glob.glob(os.path.join(source_dir, "*.h")) +
        _glob.glob(os.path.join(source_dir, "*.hpp"))
    )
    print(f"  Scanning {len(source_files)} source files for #ifdef guards...")

    guards = extract_source_guards(source_files)
    print(f"  Found {len(guards)} preprocessor guard regions:")
    for g in guards:
        print(f"    #{g['directive']} {g['guard']} -> {os.path.basename(g['file'])}:{g['start_line']}-{g['end_line']}")

    # --- Step 6: Correlate and Report ---
    print(f"\n{'=' * 70}")
    print("  STEP 6: Correlating Coverage with Feature Guards")
    print("=" * 70)

    dead_features = find_dead_features(per_config_cov, guards, source_files)
    generate_report(dead_features, per_config_cov, source_files)

    elapsed = time.time() - start_time
    print(f"\n  Total analysis time: {elapsed:.1f} seconds")
    print(f"  Pipeline complete.\n")


if __name__ == "__main__":
    main()
