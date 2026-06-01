"""
Instrumented Builder - Builds and runs C/C++ targets with LLVM
source-based code coverage instrumentation for each configuration.
"""
import os
import subprocess
import shutil
import sys
import glob


def build_and_run(config, source_dir, build_root, config_id, binary_name='testbed'):
    """
    Compile and execute a single configuration with LLVM instrumentation.
    
    Uses direct clang++ invocation (bypassing CMake for the build step)
    to inject -fprofile-instr-generate and -fcoverage-mapping.
    The -D flags corresponding to ON features are passed as preprocessor defines.
    
    Args:
        config: dict mapping flag_name -> 'ON'|'OFF'
        source_dir: path to the directory containing source files
        build_root: root directory for all build outputs
        config_id: integer ID for this configuration
        binary_name: name of the output binary (without extension)
    
    Returns:
        tuple (success: bool, build_dir: str)
    """
    build_dir = os.path.join(build_root, f"build_{config_id}")
    if os.path.exists(build_dir):
        shutil.rmtree(build_dir)
    os.makedirs(build_dir)

    # Prepare -D flags for ON features only
    define_args = []
    for k, v in config.items():
        if v == "ON":
            define_args.append(f"-D{k}")

    # LLVM source-based code coverage instrumentation flags
    instr_flags = ["-fprofile-instr-generate", "-fcoverage-mapping"]

    # Find all .cpp and .c files in source_dir
    source_files = (
        glob.glob(os.path.join(source_dir, "*.cpp")) +
        glob.glob(os.path.join(source_dir, "*.c"))
    )
    if not source_files:
        print(f"--- Config {config_id} Failed: No source files found in {source_dir} ---")
        return False, build_dir

    binary_ext = ".exe" if os.name == 'nt' else ""
    binary_path = os.path.join(build_dir, f"{binary_name}{binary_ext}")

    compile_cmd = (
        ["clang++"] + source_files + define_args + instr_flags +
        ["-o", binary_path]
    )

    print(f"--- Building Config {config_id}: {config} ---")

    try:
        # Compile
        result = subprocess.run(
            compile_cmd, cwd=build_dir,
            check=True, capture_output=True, text=True
        )
        if not os.path.exists(binary_path):
            print(f"--- Config {config_id} Failed: Binary not found at {binary_path} ---")
            return False, build_dir

        # Set profile output path
        env = os.environ.copy()
        env["LLVM_PROFILE_FILE"] = os.path.join(
            build_dir, f"code-{config_id}-%p.profraw"
        )

        # Execute the instrumented binary
        print(f"--- Running Config {config_id} ---")
        subprocess.run(
            [binary_path], cwd=build_dir, env=env,
            check=True, capture_output=True, text=True,
            timeout=30  # Prevent hanging on infinite loops
        )

        print(f"--- Config {config_id} Success ---")
        return True, build_dir

    except subprocess.TimeoutExpired:
        print(f"--- Config {config_id} Timed Out ---")
        return False, build_dir
    except subprocess.CalledProcessError as e:
        print(f"--- Config {config_id} Failed ---")
        print(f"  stdout: {e.stdout}")
        print(f"  stderr: {e.stderr}")
        return False, build_dir
    except Exception as e:
        print(f"--- Config {config_id} Failed (unexpected): {e} ---")
        return False, build_dir
