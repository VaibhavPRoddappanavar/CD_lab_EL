"""
Tests for the Matrix Orchestrator module.
"""
import pytest
import sys
import os

# Add src to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'src')))

from orchestrator import generate_matrix, matrix_summary


class TestGenerateMatrix:
    """Tests for build matrix generation."""

    def test_two_flags(self):
        """Standard case with 2 flags."""
        base_flags = {'FEATURE_A': 'OFF', 'FEATURE_B': 'OFF'}
        matrix = generate_matrix(base_flags)

        # Should have: All-Off, All-On, A-only, B-only, A+B pair
        # But A+B pair == All-On for 2 flags, so deduplicated
        expected_configs = [
            {'FEATURE_A': 'OFF', 'FEATURE_B': 'OFF'},  # All-Off
            {'FEATURE_A': 'ON', 'FEATURE_B': 'ON'},    # All-On
            {'FEATURE_A': 'ON', 'FEATURE_B': 'OFF'},   # A-only
            {'FEATURE_A': 'OFF', 'FEATURE_B': 'ON'},   # B-only
        ]
        for config in expected_configs:
            assert config in matrix, f"Expected config {config} not in matrix"
        assert len(matrix) == len(expected_configs)

    def test_three_flags(self):
        """Three flags should produce pairwise combinations."""
        base_flags = {'A': 'OFF', 'B': 'OFF', 'C': 'OFF'}
        matrix = generate_matrix(base_flags)

        # 2 (all-off, all-on) + 3 (single toggles) + 3 (pairwise) = 8
        assert len(matrix) == 8

        # Verify pairwise configs exist
        assert {'A': 'ON', 'B': 'ON', 'C': 'OFF'} in matrix
        assert {'A': 'ON', 'B': 'OFF', 'C': 'ON'} in matrix
        assert {'A': 'OFF', 'B': 'ON', 'C': 'ON'} in matrix

    def test_single_flag(self):
        """Single flag produces only 2 configs (All-Off and All-On)."""
        base_flags = {'ONLY_FLAG': 'OFF'}
        matrix = generate_matrix(base_flags)
        assert len(matrix) == 2
        assert {'ONLY_FLAG': 'OFF'} in matrix
        assert {'ONLY_FLAG': 'ON'} in matrix

    def test_empty_flags(self):
        """Empty flags should return a single empty config."""
        matrix = generate_matrix({})
        assert matrix == [{}]

    def test_no_duplicates(self):
        """Ensure no duplicate configurations exist."""
        base_flags = {'A': 'OFF', 'B': 'OFF', 'C': 'OFF', 'D': 'OFF'}
        matrix = generate_matrix(base_flags)
        for i, config in enumerate(matrix):
            for j, other in enumerate(matrix):
                if i != j:
                    assert config != other, f"Duplicate at indices {i} and {j}"

    def test_large_flag_set_no_pairwise(self):
        """Flag sets > 10 should skip pairwise to avoid explosion."""
        base_flags = {f'FLAG_{i}': 'OFF' for i in range(15)}
        matrix = generate_matrix(base_flags)
        # 2 (base) + 15 (single toggles) = 17
        assert len(matrix) == 17

    def test_all_configs_have_correct_keys(self):
        """Every config must have exactly the same keys."""
        base_flags = {'X': 'ON', 'Y': 'OFF', 'Z': 'ON'}
        matrix = generate_matrix(base_flags)
        for config in matrix:
            assert set(config.keys()) == {'X', 'Y', 'Z'}

    def test_values_only_on_off(self):
        """All values should be either 'ON' or 'OFF'."""
        base_flags = {'A': 'OFF', 'B': 'ON'}
        matrix = generate_matrix(base_flags)
        for config in matrix:
            for v in config.values():
                assert v in ('ON', 'OFF')


class TestMatrixSummary:
    """Tests for human-readable matrix summary."""

    def test_summary_format(self):
        """Summary should list ON flags for each config."""
        matrix = [
            {'A': 'OFF', 'B': 'OFF'},
            {'A': 'ON', 'B': 'ON'},
        ]
        summary = matrix_summary(matrix, ['A', 'B'])
        assert 'Config 0' in summary
        assert 'Config 1' in summary
        assert '(none)' in summary
        assert 'A' in summary
        assert 'B' in summary
