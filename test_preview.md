# Dead Feature Detector - Test & Verification Guide

This document provides a comprehensive guide to testing the **Dead Feature Detector** from scratch, including environment setup, execution steps, and verification of objectives.

---

## 1. Prerequisites & Installation

To run this tool, you need a C++ development environment with the **LLVM/Clang** toolchain, as it relies on LLVM's source-based code coverage.

### Required Software:
- **Python 3.8+**
- **CMake 3.10+**
- **LLVM/Clang** (Must include `clang++`, `llvm-profdata`, and `llvm-cov`)
  - *Windows:* Install via [LLVM Releases](https://github.com/llvm/llvm-project/releases) or `choco install llvm`.
  - *Linux:* `sudo apt install clang llvm`
  - *macOS:* `brew install llvm`

### Verify Toolchain:
Ensure these commands work in your terminal:
```bash
clang++ --version
cmake --version
llvm-profdata --version
llvm-cov --version
```

---

## 2. Testing the System (Step-by-Step)

### Step 1: Initialize the Environment
The tool uses a synthetic testbed provided in the repository to demonstrate detection.
```bash
# Ensure you are in the project root
ls testbed/  # Should see main.cpp and CMakeLists.txt
```

### Step 2: Run the Detector
Run the main orchestrator. It will automatically scout flags, generate the build matrix, build the testbed multiple times with instrumentation, and analyze the results.
```bash
python src/main.py
```

### Step 3: Observe the Process
As the tool runs, you will see the following phases in the console:
1.  **Scouting Flags:** Identifying `FEATURE_A`, `FEATURE_B`, and `DEAD_FEATURE` from CMake.
2.  **Generating Matrix:** Creating configurations (e.g., All-Off, All-On, Toggle FEATURE_A).
3.  **Executing Builds:** Building the `testbed` binary for each config using `clang++`.
4.  **Analyzing Coverage:** Merging `.profraw` files and running `llvm-cov`.

---

## 3. Expected Outputs

### Console Summary:
At the end of the run, the tool should output:
- A list of discovered feature flags.
- A success count of builds (e.g., "Completed 5/5 builds successfully").
- A **Coverage Report Summary** showing 0% coverage for regions guarded by `DEAD_FEATURE`.

### Artifacts (in `multi_build/` folder):
- `build_0/`, `build_1/`, etc.: Isolated build environments for each test case.
- `merged.profdata`: The aggregated dynamic execution data from all runs.
- `build_X/code-X-PID.profraw`: Raw profile data for each specific configuration.

---

## 4. Objective Mapping (How it matches Assignment 29)

| Objective | Implementation Proof |
| :--- | :--- |
| **1. Build Config Extractor** | `src/scout.py` uses `cmake -LA` to programmatically extract all `#define` equivalents (Options/Cache vars) used in the build system. |
| **2. Correlated Analysis** | `src/builder.py` injects LLVM IR-level instrumentation. `src/analyzer.py` correlates this IR reachability with the build-time configuration matrix. |
| **3. Dead Feature Report** | The final output identifies code blocks (via `llvm-cov`) that remain at 0 coverage across all real build combinations. |
| **4. Large-Scale Evaluation** | The tool is designed as a generic wrapper; while tested on `testbed`, it can be pointed at any CMake project (like `zlib` or `googletest`) by changing the `source_dir` in `src/main.py`. |
| **5. Impact Estimation** | `src/analyzer.py` calculates the number of zero-coverage lines, which directly maps to SLOC and binary size reduction potential. |

---

## 5. Troubleshooting
- **"clang++ not found":** Ensure LLVM is in your System PATH.
- **"No profile data found":** Ensure the binary executed successfully. If `testbed` crashes or doesn't run, `.profraw` files won't be generated.
- **Windows Pathing:** If you are on Windows, the tool handles `.exe` suffixes and `Debug/` folders automatically.
