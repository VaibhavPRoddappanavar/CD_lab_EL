# Dead Feature Detector for C/C++ Codebases

## Demo Video

<div align="center">
  <video src="demo/CD_LAB_EL_Demo.mp4" controls="controls" style="max-width: 100%;">
    Your browser does not support the video tag.
  </video>
</div>

A whole-program analysis tool that identifies code regions guarded by preprocessor
flags (`#ifdef`, `#ifndef`, `#if defined(...)`) that are unreachable across all
realistic build configurations — beyond what normal compiler dead-code elimination
can detect.

## How It Works

1. **Scout:** Extracts feature flags from CMake build system (`cmake -LA`)
2. **Matrix:** Generates build configurations using Delta-Sampling (All-Off, All-On, Single-Toggle, Pairwise)
3. **Build:** Compiles and runs each configuration with LLVM source-based code coverage
4. **Analyze:** Per-configuration coverage analysis via `llvm-cov export` (JSON)
5. **Correlate:** Cross-references coverage data with source-level `#ifdef` guards
6. **Report:** Generates dead-feature report with confidence scores and SLOC estimates

## Prerequisites

- **Python 3.8+**
- **CMake 3.10+**
- **LLVM/Clang** (includes `clang++`, `llvm-profdata`, `llvm-cov`)

## Quick Start

```bash
# Verify toolchain
clang++ --version
cmake --version
llvm-profdata --version

# Run the detector on the included testbed
python src/main.py

# Run unit tests
python -m pytest tests/ -v
```

## Project Structure

```
src/
  main.py          # Pipeline orchestrator (entry point)
  scout.py         # CMake flag extraction + source guard parsing
  orchestrator.py  # Build configuration matrix generation
  builder.py       # Instrumented compilation and execution
  analyzer.py      # Per-config coverage analysis + dead feature detection
testbed/
  main.cpp         # Synthetic test project with feature guards
  CMakeLists.txt   # CMake build with FEATURE_A, FEATURE_B, DEAD_FEATURE options
tests/
  test_scout.py        # 12 tests for flag extraction and guard parsing
  test_orchestrator.py  # 9 tests for matrix generation
  test_analyzer.py      # 9 tests for coverage analysis and correlation
```

## Environment Variables

| Variable | Default | Description |
|:---|:---|:---|
| `DFD_SOURCE_DIR` | `testbed/` | Path to the C/C++ project to analyze |
| `DFD_BUILD_ROOT` | `build_matrix/` | Output directory for builds |
| `DFD_BINARY_NAME` | `testbed` | Name of the compiled binary |