"""
Tests for the Config Scout module.
"""
import pytest
from unittest.mock import MagicMock, patch
import sys
import os
import tempfile

# Add src to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'src')))

from scout import scout_flags, filter_flags, extract_source_guards


class TestScoutFlags:
    """Tests for cmake flag extraction."""

    def test_scout_flags_parsing(self):
        """Verify that BOOL-typed cache variables are correctly extracted."""
        mock_stdout = (
            "CMAKE_BUILD_TYPE:STRING=Release\n"
            "FEATURE_A:BOOL=ON\n"
            "FEATURE_B:BOOL=OFF\n"
            "CMAKE_INSTALL_PREFIX:PATH=/usr/local\n"
        )
        with patch('subprocess.run') as mock_run:
            mock_run.return_value = MagicMock(stdout=mock_stdout, returncode=0)
            flags = scout_flags('dummy_build_dir')
            assert flags == {'FEATURE_A': 'ON', 'FEATURE_B': 'OFF'}

    def test_scout_flags_empty_output(self):
        """Handle empty cmake output gracefully."""
        with patch('subprocess.run') as mock_run:
            mock_run.return_value = MagicMock(stdout="", returncode=0)
            flags = scout_flags('dummy_build_dir')
            assert flags == {}

    def test_scout_flags_no_bool_flags(self):
        """Non-BOOL flags should be ignored."""
        mock_stdout = "CMAKE_BUILD_TYPE:STRING=Release\nCMAKE_INSTALL_PREFIX:PATH=/usr\n"
        with patch('subprocess.run') as mock_run:
            mock_run.return_value = MagicMock(stdout=mock_stdout, returncode=0)
            flags = scout_flags('dummy_build_dir')
            assert flags == {}

    def test_scout_flags_many_flags(self):
        """Handle a large number of flags."""
        lines = [f"FLAG_{i}:BOOL={'ON' if i % 2 == 0 else 'OFF'}" for i in range(100)]
        mock_stdout = "\n".join(lines)
        with patch('subprocess.run') as mock_run:
            mock_run.return_value = MagicMock(stdout=mock_stdout, returncode=0)
            flags = scout_flags('dummy_build_dir')
            assert len(flags) == 100


class TestFilterFlags:
    """Tests for flag filtering logic."""

    def test_filter_flags_basic(self):
        """Standard feature-like flags should be retained."""
        flags = {
            'FEATURE_A': 'ON',
            'ENABLE_B': 'OFF',
            'WITH_C': 'ON',
            'BUILD_D': 'OFF',
            'DEAD_E': 'ON',
            'CMAKE_SKIP_RPATH': 'ON',
            'SOME_OTHER_FLAG': 'OFF'
        }
        filtered = filter_flags(flags)
        expected = {
            'FEATURE_A': 'ON',
            'ENABLE_B': 'OFF',
            'WITH_C': 'ON',
            'BUILD_D': 'OFF',
            'DEAD_E': 'ON'
        }
        assert filtered == expected

    def test_filter_flags_empty(self):
        """Empty input should return empty output."""
        assert filter_flags({}) == {}

    def test_filter_flags_no_match(self):
        """Flags not matching any pattern should be excluded."""
        flags = {'CMAKE_CXX_STANDARD': 'ON', 'RANDOM_FLAG': 'OFF'}
        assert filter_flags(flags) == {}

    def test_filter_flags_case_insensitive(self):
        """Matching should be case-insensitive."""
        flags = {'feature_x': 'ON', 'Enable_Y': 'OFF'}
        filtered = filter_flags(flags)
        assert 'feature_x' in filtered
        assert 'Enable_Y' in filtered

    def test_filter_flags_extended_patterns(self):
        """New patterns (USE_, HAS_, HAVE_, SUPPORT_) should also match."""
        flags = {
            'USE_OPENSSL': 'ON',
            'HAS_THREADS': 'OFF',
            'HAVE_ZLIB': 'ON',
            'SUPPORT_AVX2': 'OFF',
        }
        filtered = filter_flags(flags)
        assert len(filtered) == 4


class TestExtractSourceGuards:
    """Tests for preprocessor guard extraction."""

    def test_simple_ifdef(self):
        """Extract a simple #ifdef ... #endif block."""
        src = "#ifdef FEATURE_A\ncode();\n#endif\n"
        with tempfile.NamedTemporaryFile(mode='w', suffix='.cpp', delete=False) as f:
            f.write(src)
            f.flush()
            guards = extract_source_guards([f.name])
        os.unlink(f.name)
        assert len(guards) == 1
        assert guards[0]['guard'] == 'FEATURE_A'
        assert guards[0]['directive'] == 'ifdef'

    def test_nested_ifdefs(self):
        """Extract nested #ifdef blocks."""
        src = (
            "#ifdef FEATURE_A\n"
            "code_a();\n"
            "  #ifdef FEATURE_B\n"
            "  code_b();\n"
            "  #endif\n"
            "#endif\n"
        )
        with tempfile.NamedTemporaryFile(mode='w', suffix='.cpp', delete=False) as f:
            f.write(src)
            f.flush()
            guards = extract_source_guards([f.name])
        os.unlink(f.name)
        assert len(guards) == 2
        guard_names = {g['guard'] for g in guards}
        assert 'FEATURE_A' in guard_names
        assert 'FEATURE_B' in guard_names

    def test_ifdef_else(self):
        """Extract #ifdef ... #else ... #endif blocks."""
        src = (
            "#ifdef FEATURE_A\n"
            "path_a();\n"
            "#else\n"
            "path_b();\n"
            "#endif\n"
        )
        with tempfile.NamedTemporaryFile(mode='w', suffix='.cpp', delete=False) as f:
            f.write(src)
            f.flush()
            guards = extract_source_guards([f.name])
        os.unlink(f.name)
        # Should find two guard regions: the #ifdef block and the #else block
        assert len(guards) == 2

    def test_ifndef(self):
        """Extract #ifndef guard."""
        src = "#ifndef GUARD_H\n#define GUARD_H\ncode();\n#endif\n"
        with tempfile.NamedTemporaryFile(mode='w', suffix='.cpp', delete=False) as f:
            f.write(src)
            f.flush()
            guards = extract_source_guards([f.name])
        os.unlink(f.name)
        assert len(guards) == 1
        assert guards[0]['guard'] == 'GUARD_H'
        assert guards[0]['directive'] == 'ifndef'

    def test_if_defined(self):
        """Extract #if defined(FEATURE) guard."""
        src = "#if defined(FEATURE_X)\ncode();\n#endif\n"
        with tempfile.NamedTemporaryFile(mode='w', suffix='.cpp', delete=False) as f:
            f.write(src)
            f.flush()
            guards = extract_source_guards([f.name])
        os.unlink(f.name)
        assert len(guards) == 1
        assert guards[0]['guard'] == 'FEATURE_X'

    def test_no_guards(self):
        """File with no guards returns empty list."""
        src = "int main() { return 0; }\n"
        with tempfile.NamedTemporaryFile(mode='w', suffix='.cpp', delete=False) as f:
            f.write(src)
            f.flush()
            guards = extract_source_guards([f.name])
        os.unlink(f.name)
        assert guards == []

    def test_nonexistent_file(self):
        """Non-existent file is silently skipped."""
        guards = extract_source_guards(['/nonexistent/file.cpp'])
        assert guards == []
