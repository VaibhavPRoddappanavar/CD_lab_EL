"""
Config Scout - CMake flag extraction and source-level preprocessor analysis.

Discovers build-system feature flags via cmake -LA, filters for
feature-like options, and extracts #ifdef/#ifndef guards from source files.
"""
import subprocess
import re
import os


def scout_flags(build_dir):
    """
    Extract all BOOL-typed cache variables from a CMake build directory.
    Uses `cmake -LA` which lists all non-advanced cache variables.
    
    Returns: dict mapping flag_name -> 'ON'|'OFF'
    """
    result = subprocess.run(
        ['cmake', '-LA', build_dir],
        capture_output=True, text=True
    )
    flags = {}
    for line in result.stdout.splitlines():
        match = re.match(r'^([^:]+):BOOL=(ON|OFF)', line)
        if match:
            flags[match.group(1)] = match.group(2)
    return flags


def filter_flags(flags):
    """
    Filter flags to retain only those matching common feature-flag naming
    conventions (FEATURE_, ENABLE_, WITH_, BUILD_, DEAD_, USE_, HAS_, HAVE_,
    SUPPORT_, INCLUDE_).
    
    This prevents internal CMake flags (like CMAKE_SKIP_RPATH) from
    polluting the configuration matrix.
    """
    patterns = [
        r'FEATURE_', r'ENABLE_', r'WITH_', r'BUILD_', r'DEAD_',
        r'USE_', r'HAS_', r'HAVE_', r'SUPPORT_', r'INCLUDE_'
    ]
    return {
        k: v for k, v in flags.items()
        if any(re.search(p, k, re.IGNORECASE) for p in patterns)
    }


def extract_source_guards(source_files):
    """
    Parse C/C++ source files to extract preprocessor guard regions.
    Returns a list of dicts describing each guarded region:
      {
        'file': str,
        'guard': str,         # e.g. 'FEATURE_A'
        'directive': str,     # 'ifdef' | 'ifndef' | 'if defined(...)'
        'start_line': int,
        'end_line': int,
        'nesting_depth': int
      }
    """
    guards = []
    ifdef_pattern = re.compile(
        r'^\s*#\s*(ifdef|ifndef|if)\s+(.*)', re.MULTILINE
    )

    for fpath in source_files:
        if not os.path.isfile(fpath):
            continue
        with open(fpath, 'r', encoding='utf-8', errors='replace') as f:
            lines = f.readlines()

        stack = []  # (directive, guard_name, start_line, depth)
        depth = 0

        for i, line in enumerate(lines, start=1):
            stripped = line.strip()

            # Track #ifdef / #ifndef / #if defined(...)
            m_ifdef = re.match(r'^#\s*ifdef\s+(\w+)', stripped)
            m_ifndef = re.match(r'^#\s*ifndef\s+(\w+)', stripped)
            m_if_defined = re.match(r'^#\s*if\s+defined\s*\(\s*(\w+)\s*\)', stripped)
            m_if_plain = re.match(r'^#\s*if\s+(\w+)\s*$', stripped)

            if m_ifdef:
                stack.append(('ifdef', m_ifdef.group(1), i, depth))
                depth += 1
            elif m_ifndef:
                stack.append(('ifndef', m_ifndef.group(1), i, depth))
                depth += 1
            elif m_if_defined:
                stack.append(('if_defined', m_if_defined.group(1), i, depth))
                depth += 1
            elif m_if_plain:
                stack.append(('if', m_if_plain.group(1), i, depth))
                depth += 1
            elif re.match(r'^#\s*elif', stripped):
                # Close current block, open new one
                if stack:
                    directive, guard, start, d = stack.pop()
                    guards.append({
                        'file': fpath,
                        'guard': guard,
                        'directive': directive,
                        'start_line': start,
                        'end_line': i - 1,
                        'nesting_depth': d,
                    })
                m_elif_def = re.match(r'^#\s*elif\s+defined\s*\(\s*(\w+)\s*\)', stripped)
                if m_elif_def:
                    stack.append(('elif_defined', m_elif_def.group(1), i, depth - 1))
                else:
                    stack.append(('elif', 'COMPLEX_EXPR', i, depth - 1))
            elif re.match(r'^#\s*else', stripped):
                if stack:
                    directive, guard, start, d = stack.pop()
                    guards.append({
                        'file': fpath,
                        'guard': guard,
                        'directive': directive,
                        'start_line': start,
                        'end_line': i - 1,
                        'nesting_depth': d,
                    })
                    # The #else block negates the previous guard
                    neg_directive = 'else_' + directive
                    stack.append((neg_directive, guard, i, d))
            elif re.match(r'^#\s*endif', stripped):
                depth -= 1
                if stack:
                    directive, guard, start, d = stack.pop()
                    guards.append({
                        'file': fpath,
                        'guard': guard,
                        'directive': directive,
                        'start_line': start,
                        'end_line': i,
                        'nesting_depth': d,
                    })

    return guards
