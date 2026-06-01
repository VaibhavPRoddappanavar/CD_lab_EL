"""
Matrix Orchestrator - Build configuration matrix generation.

Generates a set of build configurations using Delta-Sampling strategy
to achieve maximum feature-space coverage with minimal builds.
"""
import itertools


def generate_matrix(base_flags):
    """
    Generates a list of configurations (dictionaries) using Delta-Sampling:
    1. All-Off: All flags set to OFF.
    2. All-On: All flags set to ON.
    3. Single-Toggle: Each flag toggled individually from All-Off baseline.
    4. Pairwise (for small flag sets): All pairs toggled ON together.
    
    For N flags, this produces: 2 + N + C(N,2) configs (deduplicated).
    For large N (>10), pairwise is skipped to avoid combinatorial explosion.
    """
    if not base_flags:
        return [{}]
    
    matrix = []
    flag_names = list(base_flags.keys())

    # 1. All-Off
    matrix.append({k: 'OFF' for k in flag_names})

    # 2. All-On
    matrix.append({k: 'ON' for k in flag_names})

    # 3. Single-Toggle (each flag ON individually, rest OFF)
    for flag in flag_names:
        config = {k: 'OFF' for k in flag_names}
        config[flag] = 'ON'
        matrix.append(config)

    # 4. Pairwise-Toggle (each pair ON together) - only for small flag sets
    if len(flag_names) <= 10:
        for f1, f2 in itertools.combinations(flag_names, 2):
            config = {k: 'OFF' for k in flag_names}
            config[f1] = 'ON'
            config[f2] = 'ON'
            matrix.append(config)

    # Deduplicate
    unique_matrix = []
    for m in matrix:
        if m not in unique_matrix:
            unique_matrix.append(m)

    return unique_matrix


def matrix_summary(matrix, flag_names):
    """
    Returns a human-readable summary of the configuration matrix.
    """
    lines = []
    for i, config in enumerate(matrix):
        on_flags = [k for k, v in config.items() if v == 'ON']
        label = ', '.join(on_flags) if on_flags else '(none)'
        lines.append(f"  Config {i}: ON=[{label}]")
    return '\n'.join(lines)
