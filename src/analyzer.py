"""
Reachability Analyzer - Per-configuration coverage analysis and
dead-feature correlation engine.

CRITICAL DESIGN NOTE:
The original implementation merged ALL .profraw files into a single
merged.profdata and analyzed against a single binary (build_1, the All-On build).
This is FUNDAMENTALLY INCORRECT because:

1. Each configuration compiles DIFFERENT code (different #ifdefs are active).
2. The All-On binary includes ALL feature code, so its coverage mapping
   covers all possible lines.
3. Merging profiles from differently-compiled binaries into one and then
   analyzing against the All-On binary makes ALL lines appear executed
   because SOME configuration always executes each line.

CORRECT APPROACH (implemented here):
- For EACH configuration, analyze coverage INDEPENDENTLY using THAT
  configuration's binary + THAT configuration's profraw.
- Use `llvm-cov export` (JSON format) instead of parsing `llvm-cov show` text
  output, which is fragile and platform-dependent.
- A line is "dead across all configurations" only if it appears in at
  least one configuration's coverage map but has 0 execution count in
  EVERY configuration where it is compiled.
- We then correlate these dead lines with preprocessor guards to identify
  dead FEATURES (not just dead lines).
"""
import subprocess
import glob
import os
import re
import json


def analyze_per_config_coverage(build_root, binary_name):
    """
    Analyze coverage for EACH build configuration independently using
    `llvm-cov export` (JSON output) for reliability.
    
    Returns a dict:
      {
        config_id: {
          'binary': str,
          'profdata': str,
          'coverage_lines': {
            filepath: { line_no: execution_count, ... }
          },
          'functions': [ { name, count, regions, filenames } ],
          'summary': { lines, functions, regions }
        }
      }
    """
    build_dirs = sorted(glob.glob(os.path.join(build_root, "build_*")))
    if not build_dirs:
        print("No build directories found.")
        return {}

    binary_ext = ".exe" if os.name == 'nt' else ""
    configs = {}

    for bdir in build_dirs:
        # Extract config ID from directory name
        dirname = os.path.basename(bdir)
        match = re.match(r'build_(\d+)', dirname)
        if not match:
            continue
        config_id = int(match.group(1))

        binary_path = os.path.join(bdir, f"{binary_name}{binary_ext}")
        profraw_files = glob.glob(os.path.join(bdir, "*.profraw"))

        if not os.path.exists(binary_path):
            print(f"  Config {config_id}: Binary not found, skipping.")
            continue
        if not profraw_files:
            print(f"  Config {config_id}: No .profraw files, skipping.")
            continue

        # Merge profraw files for THIS config into per-config profdata
        profdata_path = os.path.join(bdir, f"config_{config_id}.profdata")
        try:
            subprocess.run(
                ['llvm-profdata', 'merge', '-sparse'] + profraw_files +
                ['-o', profdata_path],
                check=True, capture_output=True, text=True
            )
        except subprocess.CalledProcessError as e:
            print(f"  Config {config_id}: Failed to merge profile data: {e.stderr}")
            continue

        # Use llvm-cov export (JSON) for reliable, parseable output
        try:
            result = subprocess.run(
                ['llvm-cov', 'export', binary_path,
                 f'-instr-profile={profdata_path}'],
                capture_output=True, text=True, check=True
            )
        except subprocess.CalledProcessError as e:
            print(f"  Config {config_id}: llvm-cov export failed: {e.stderr}")
            continue

        try:
            cov_data = json.loads(result.stdout)
        except json.JSONDecodeError as e:
            print(f"  Config {config_id}: Failed to parse coverage JSON: {e}")
            continue

        # Parse the JSON coverage data into per-line counts
        coverage_lines, functions, summary = parse_coverage_json(cov_data)

        configs[config_id] = {
            'binary': binary_path,
            'profdata': profdata_path,
            'coverage_lines': coverage_lines,
            'functions': functions,
            'summary': summary,
        }

        total_lines = sum(len(v) for v in coverage_lines.values())
        total_files = len(coverage_lines)
        print(f"  Config {config_id}: Analyzed {total_lines} lines across {total_files} files.")

    return configs


def parse_coverage_json(cov_data):
    """
    Parse `llvm-cov export` JSON output into structured per-line coverage data.
    
    The JSON format (version 2.0.1) has:
    - data[0].files[].filename
    - data[0].files[].segments: [[line, col, count, hasCount, isRegionEntry, isGapRegion], ...]
    - data[0].functions[].name, .count, .regions, .filenames
    
    Segments represent coverage regions. To compute per-line counts, we need to
    track active regions and their counts as we walk through lines.
    
    Returns:
        (coverage_lines, functions, summary)
        coverage_lines: { filepath: { line_no: count } }
        functions: list of function dicts
        summary: summary dict
    """
    coverage_lines = {}
    functions = []
    summary = {}

    for export in cov_data.get('data', []):
        # Parse file-level data
        for file_data in export.get('files', []):
            filename = os.path.normpath(file_data.get('filename', ''))
            segments = file_data.get('segments', [])
            file_summary = file_data.get('summary', {})

            if not filename:
                continue

            line_counts = compute_line_counts_from_segments(segments)
            coverage_lines[filename] = line_counts

        # Parse function-level data
        for func_data in export.get('functions', []):
            functions.append({
                'name': func_data.get('name', ''),
                'count': func_data.get('count', 0),
                'filenames': func_data.get('filenames', []),
                'regions': func_data.get('regions', []),
            })

        # Parse totals
        totals = export.get('totals', cov_data.get('totals', {}))
        summary = {
            'lines': totals.get('lines', {}),
            'functions': totals.get('functions', {}),
            'regions': totals.get('regions', {}),
        }

    return coverage_lines, functions, summary


def compute_line_counts_from_segments(segments):
    """
    Compute per-line execution counts from llvm-cov segments.
    
    Each segment is: [line, col, count, hasCount, isRegionEntry, isGapRegion]
    
    Segments define region boundaries. Between two consecutive segments,
    the count of the first segment applies to all lines in that range.
    Lines with hasCount=false are not instrumented.
    
    Returns: { line_no: max_execution_count }
    """
    if not segments:
        return {}

    line_counts = {}

    for i, seg in enumerate(segments):
        line = seg[0]
        col = seg[1]
        count = seg[2]
        has_count = seg[3] if len(seg) > 3 else True
        is_region_entry = seg[4] if len(seg) > 4 else False
        is_gap = seg[5] if len(seg) > 5 else False

        if not has_count or is_gap:
            continue

        # Determine the line range this segment covers.
        # A segment covers from its start line to the start of the next segment (exclusive).
        if i + 1 < len(segments):
            end_line = segments[i + 1][0]
        else:
            end_line = line + 1  # Last segment covers just its line

        # Assign count to lines in this segment's range (exclusive end)
        for ln in range(line, end_line):
            if ln in line_counts:
                line_counts[ln] = max(line_counts[ln], count)
            else:
                line_counts[ln] = count

    return line_counts


def find_dead_features(per_config_coverage, source_guards, source_files):
    """
    Correlate per-configuration coverage with preprocessor guards to identify
    dead features.
    
    A feature is "dead" if:
    - The code guarded by that feature's #ifdef has 0 execution count in
      EVERY configuration where it was compiled (i.e., where the flag was ON).
    
    Args:
        per_config_coverage: output from analyze_per_config_coverage()
        source_guards: output from scout.extract_source_guards()
        source_files: list of source file paths to analyze
    
    Returns:
        list of dead feature reports
    """
    dead_features = []

    for guard in source_guards:
        guard_name = guard['guard']
        guard_file = os.path.normpath(guard['file'])
        start_line = guard['start_line']
        end_line = guard['end_line']
        directive = guard['directive']

        # Only check #ifdef / #if defined() guards (not #ifndef / #else)
        if directive.startswith('else_') or directive == 'ifndef':
            continue

        # For each configuration, check if the lines in the guard range were executed.
        configs_with_flag_on = []
        configs_with_zero_coverage = []
        total_guard_lines = 0
        total_zero_lines = 0

        for config_id, config_data in per_config_coverage.items():
            cov = config_data.get('coverage_lines', {})

            # Check if this file appears in this config's coverage
            file_cov = None
            for fpath, line_data in cov.items():
                if os.path.normpath(fpath) == guard_file:
                    file_cov = line_data
                    break

            if file_cov is None:
                continue

            # Check if lines within the guard range have any coverage data.
            # Use start_line < ln < end_line to exclude directive lines.
            # For very small guards (1 line between #ifdef and #endif),
            # also include start_line+1 == end_line-1 case.
            guard_lines_in_cov = {
                ln: cnt for ln, cnt in file_cov.items()
                if start_line < ln < end_line
            }

            # For single-line guards where start_line+1 == end_line,
            # there are no interior lines. Check if the guard line itself
            # or start_line+1 has coverage data (the code is ON that line).
            if not guard_lines_in_cov and (end_line - start_line <= 2):
                # Try checking start_line+1 specifically
                check_line = start_line + 1
                if check_line in file_cov:
                    guard_lines_in_cov = {check_line: file_cov[check_line]}

            if not guard_lines_in_cov:
                # This flag was likely OFF for this config (no lines inside guard)
                continue

            configs_with_flag_on.append(config_id)
            total_guard_lines += len(guard_lines_in_cov)

            zero_lines = [ln for ln, cnt in guard_lines_in_cov.items() if cnt == 0]
            total_zero_lines += len(zero_lines)

            if len(zero_lines) == len(guard_lines_in_cov):
                # ALL instrumented lines in this guard were 0 for this config
                configs_with_zero_coverage.append(config_id)

        if not configs_with_flag_on:
            # Flag was never ON in any configuration - definitely dead
            dead_features.append({
                'guard': guard_name,
                'file': guard_file,
                'start_line': start_line,
                'end_line': end_line,
                'directive': directive,
                'reason': 'never_compiled',
                'confidence': 1.0,
                'configs_tested': 0,
                'configs_dead': 0,
                'dead_lines': max(0, end_line - start_line - 1),
                'detail': f"Guard '{guard_name}' was never enabled in any tested configuration.",
            })
        elif len(configs_with_zero_coverage) == len(configs_with_flag_on):
            # Code was compiled but NEVER executed in any config where flag was ON
            confidence = min(1.0, len(configs_with_flag_on) / max(1, len(per_config_coverage)))
            dead_features.append({
                'guard': guard_name,
                'file': guard_file,
                'start_line': start_line,
                'end_line': end_line,
                'directive': directive,
                'reason': 'compiled_but_unreachable',
                'confidence': confidence,
                'configs_tested': len(configs_with_flag_on),
                'configs_dead': len(configs_with_zero_coverage),
                'dead_lines': total_zero_lines // max(1, len(configs_with_flag_on)),
                'detail': (
                    f"Guard '{guard_name}' was enabled in {len(configs_with_flag_on)} "
                    f"configurations but the guarded code had 0 execution count in all of them."
                ),
            })

    return dead_features


def generate_report(dead_features, per_config_coverage, source_files):
    """
    Generate a comprehensive dead-feature report with confidence scores,
    source locations, SLOC estimates, and remediation guidance.
    """
    print("\n" + "=" * 70)
    print("   DEAD FEATURE DETECTOR - ANALYSIS REPORT")
    print("=" * 70)

    # Summary statistics
    total_configs = len(per_config_coverage)
    total_files = len(source_files)
    total_dead = len(dead_features)

    print(f"\n  Configurations tested: {total_configs}")
    print(f"  Source files analyzed: {total_files}")
    print(f"  Dead features found:  {total_dead}")

    if not dead_features:
        print("\n  [OK] No dead features detected across all configurations.")
        print("=" * 70)
        return dead_features

    # Calculate total removable lines
    total_removable_sloc = sum(df['dead_lines'] for df in dead_features)

    # Count total instrumented lines across all configs for percentage
    total_lines = 0
    for config_data in per_config_coverage.values():
        for file_cov in config_data['coverage_lines'].values():
            total_lines = max(total_lines, len(file_cov))

    print(f"\n  Estimated removable SLOC: {total_removable_sloc}")
    if total_lines > 0:
        pct = (total_removable_sloc / total_lines) * 100
        print(f"  Code reduction potential: {pct:.1f}%")

    # Detailed findings
    print(f"\n{'-' * 70}")
    print("  DETAILED FINDINGS")
    print(f"{'-' * 70}")

    for i, df in enumerate(dead_features, 1):
        confidence_bar = "#" * int(df['confidence'] * 10) + "." * (10 - int(df['confidence'] * 10))
        confidence_pct = df['confidence'] * 100

        print(f"\n  [{i}] DEAD FEATURE: {df['guard']}")
        print(f"      File:       {df['file']}")
        print(f"      Lines:      {df['start_line']} - {df['end_line']}")
        print(f"      Directive:  #{df['directive']}")
        print(f"      Reason:     {df['reason']}")
        print(f"      Confidence: [{confidence_bar}] {confidence_pct:.0f}%")
        print(f"      Dead SLOC:  {df['dead_lines']}")
        print(f"      Detail:     {df['detail']}")

        # Risk classification
        if df['confidence'] >= 0.9:
            risk = "LOW RISK - Safe to remove"
        elif df['confidence'] >= 0.6:
            risk = "MEDIUM RISK - Review before removal"
        else:
            risk = "HIGH RISK - Needs manual verification"
        print(f"      Risk:       {risk}")

    # Binary size estimate (rough: ~20 bytes per SLOC for compiled C++)
    est_binary_savings = total_removable_sloc * 20
    print(f"\n{'-' * 70}")
    print("  IMPACT ESTIMATION")
    print(f"{'-' * 70}")
    print(f"  Removable source lines: {total_removable_sloc}")
    print(f"  Est. binary savings:    ~{est_binary_savings} bytes ({est_binary_savings/1024:.1f} KB)")
    if dead_features:
        print(f"  Confidence range:       {min(df['confidence'] for df in dead_features)*100:.0f}% - {max(df['confidence'] for df in dead_features)*100:.0f}%")

    print("\n" + "=" * 70)

    return dead_features
