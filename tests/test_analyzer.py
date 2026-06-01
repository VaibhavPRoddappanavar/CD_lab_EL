"""
Tests for the Reachability Analyzer module.
"""
import pytest
import sys
import os

# Add src to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'src')))

from analyzer import parse_coverage_json, compute_line_counts_from_segments, find_dead_features


class TestCoverageJsonParsing:
    """Tests for llvm-cov export JSON parser."""

    def test_parse_simple_json(self):
        """Parse a minimal llvm-cov export JSON structure."""
        cov_json = {
            "data": [{
                "files": [{
                    "filename": "/src/main.cpp",
                    "segments": [
                        [3, 12, 1, True, True, False],  # main() start
                        [5, 1, 0, True, True, False],    # dead line
                        [7, 2, 0, False, False, False],  # end
                    ],
                    "summary": {"lines": {"count": 5, "covered": 3}}
                }],
                "functions": [{
                    "name": "main",
                    "count": 1,
                    "filenames": ["/src/main.cpp"],
                    "regions": [[3, 12, 7, 2, 1, 0, 0, 0]],
                }],
                "totals": {
                    "lines": {"count": 5, "covered": 3},
                    "functions": {"count": 1, "covered": 1},
                    "regions": {"count": 1, "covered": 1},
                }
            }],
            "type": "llvm.coverage.json.export",
            "version": "2.0.1"
        }
        coverage_lines, functions, summary = parse_coverage_json(cov_json)
        assert len(coverage_lines) == 1
        assert os.path.normpath("/src/main.cpp") in coverage_lines
        assert len(functions) == 1
        assert functions[0]['name'] == 'main'

    def test_compute_line_counts_basic(self):
        """Compute line counts from segments."""
        # Segments that don't overlap - each starts at a distinct line
        segments = [
            [3, 12, 1, True, True, False],  # line 3, count=1, spans to line 5
            [6, 1, 0, True, True, False],    # line 6, count=0, spans to line 8
            [9, 2, 0, False, False, False],  # end marker (gap)
        ]
        counts = compute_line_counts_from_segments(segments)
        assert 3 in counts
        assert counts[3] == 1  # covered
        assert 6 in counts
        assert counts[6] == 0  # not covered

    def test_compute_line_counts_empty(self):
        """Empty segments should return empty dict."""
        assert compute_line_counts_from_segments([]) == {}

    def test_parse_empty_json(self):
        """Empty JSON should return empty results."""
        coverage_lines, functions, summary = parse_coverage_json({"data": []})
        assert coverage_lines == {}
        assert functions == []




class TestFindDeadFeatures:
    """Tests for dead feature correlation logic."""

    def test_never_compiled_feature(self):
        """A feature flag never ON in any config should be detected as dead."""
        per_config_cov = {
            0: {
                'binary': '/path/to/bin',
                'profraw': ['/path/to/prof.profraw'],
                'profdata': '/path/to/prof.profdata',
                'coverage_lines': {
                    '/src/main.cpp': {3: 1, 4: 1, 17: 1, 18: 1}
                }
            }
        }
        source_guards = [{
            'file': '/src/main.cpp',
            'guard': 'NEVER_USED',
            'directive': 'ifdef',
            'start_line': 10,
            'end_line': 15,
            'nesting_depth': 0,
        }]
        dead = find_dead_features(per_config_cov, source_guards, ['/src/main.cpp'])
        assert len(dead) == 1
        assert dead[0]['guard'] == 'NEVER_USED'
        assert dead[0]['reason'] == 'never_compiled'
        assert dead[0]['confidence'] == 1.0

    def test_compiled_but_unreachable(self):
        """Code compiled but never executed should be detected."""
        per_config_cov = {
            0: {
                'binary': '/path/bin0',
                'profraw': [],
                'profdata': '/p0.profdata',
                'coverage_lines': {
                    '/src/main.cpp': {
                        3: 1,  # main()
                        11: 0,  # inside #ifdef DEAD - line with 0 count
                        12: 0,  # inside #ifdef DEAD - line with 0 count
                        17: 1,  # return
                    }
                }
            }
        }
        source_guards = [{
            'file': '/src/main.cpp',
            'guard': 'DEAD_CODE',
            'directive': 'ifdef',
            'start_line': 10,
            'end_line': 14,
            'nesting_depth': 0,
        }]
        dead = find_dead_features(per_config_cov, source_guards, ['/src/main.cpp'])
        assert len(dead) == 1
        assert dead[0]['guard'] == 'DEAD_CODE'
        assert dead[0]['reason'] == 'compiled_but_unreachable'

    def test_live_feature_not_flagged(self):
        """Code that IS executed should NOT be flagged as dead."""
        per_config_cov = {
            0: {
                'binary': '/path/bin0',
                'profraw': [],
                'profdata': '/p0.profdata',
                'coverage_lines': {
                    '/src/main.cpp': {
                        3: 1,
                        5: 1,   # inside #ifdef LIVE_FEATURE - executed
                        6: 1,   # inside #ifdef LIVE_FEATURE - executed
                        10: 1,
                    }
                }
            }
        }
        source_guards = [{
            'file': '/src/main.cpp',
            'guard': 'LIVE_FEATURE',
            'directive': 'ifdef',
            'start_line': 4,
            'end_line': 8,
            'nesting_depth': 0,
        }]
        dead = find_dead_features(per_config_cov, source_guards, ['/src/main.cpp'])
        assert len(dead) == 0

    def test_ifndef_guards_skipped(self):
        """#ifndef guards should be skipped (they're include guards, etc.)."""
        per_config_cov = {
            0: {
                'binary': '/path/bin0',
                'profraw': [],
                'profdata': '/p0.profdata',
                'coverage_lines': {'/src/main.h': {}}
            }
        }
        source_guards = [{
            'file': '/src/main.h',
            'guard': 'MAIN_H_GUARD',
            'directive': 'ifndef',
            'start_line': 1,
            'end_line': 50,
            'nesting_depth': 0,
        }]
        dead = find_dead_features(per_config_cov, source_guards, ['/src/main.h'])
        assert len(dead) == 0

    def test_confidence_scoring(self):
        """Confidence should scale with number of configs tested."""
        cov = {}
        for i in range(10):
            cov[i] = {
                'binary': f'/bin{i}',
                'profraw': [],
                'profdata': f'/p{i}',
                'coverage_lines': {
                    '/src/main.cpp': {
                        5: 0,  # inside guard, never executed
                        6: 0,
                    }
                }
            }
        source_guards = [{
            'file': '/src/main.cpp',
            'guard': 'DEAD_FLAG',
            'directive': 'ifdef',
            'start_line': 4,
            'end_line': 8,
            'nesting_depth': 0,
        }]
        dead = find_dead_features(cov, source_guards, ['/src/main.cpp'])
        assert len(dead) == 1
        assert dead[0]['confidence'] == 1.0  # 10/10 configs tested
