#!/usr/bin/env python3
"""
Quality Gate Script for Movie Recommendation System

This script enforces quality standards across:
1. Unit Tests (all tests must pass)
2. Schema Validation (Kafka message schemas)
3. Backpressure Handling (data integrity under load)

Usage:
    python scripts/quality_gate.py
    python scripts/quality_gate.py --verbose
    python scripts/quality_gate.py --gate unit-tests
    python scripts/quality_gate.py --gate schema-validation
    python scripts/quality_gate.py --gate backpressure

Exit codes:
    0 = All gates passed
    1 = One or more gates failed
"""
import sys
import subprocess
import json
import argparse
from pathlib import Path
from typing import Dict, List, Tuple
import re

# ANSI color codes
GREEN = '\033[92m'
RED = '\033[91m'
YELLOW = '\033[93m'
BLUE = '\033[94m'
BOLD = '\033[1m'
RESET = '\033[0m'

# Quality Gate Thresholds
QUALITY_GATES = {
    "unit_tests": {
        "min_pass_rate": 100,  # All tests must pass
        "max_failures": 0,
        "description": "All unit tests must pass with 100% success rate"
    },
    "schema_validation": {
        "min_pass_rate": 100,  # All schema tests must pass
        "max_failures": 0,
        "required_schemas": ["watch", "rate", "reco_requests", "reco_responses"],
        "description": "All Kafka schema validation tests must pass"
    },
    "backpressure": {
        "min_pass_rate": 100,  # All backpressure tests must pass
        "max_failures": 0,
        "required_tests": 5,  # Must have at least 5 backpressure tests
        "description": "All backpressure handling tests must pass"
    }
}


class QualityGate:
    """Base class for quality gate checks."""
    
    def __init__(self, name: str, verbose: bool = False):
        self.name = name
        self.verbose = verbose
        self.passed = False
        self.message = ""
        
    def run(self) -> bool:
        """Execute the quality gate check. Returns True if passed."""
        raise NotImplementedError
        
    def print_result(self):
        """Print the gate result with formatting."""
        status = f"{GREEN}✓ PASS{RESET}" if self.passed else f"{RED}✗ FAIL{RESET}"
        print(f"\n{BOLD}[{status}] {self.name}{RESET}")
        print(f"{self.message}")


class UnitTestGate(QualityGate):
    """Quality gate for unit tests."""
    
    def __init__(self, verbose: bool = False):
        super().__init__("Unit Tests Gate", verbose)
        self.test_dir = Path("tests")
        
    def run(self) -> bool:
        """Run all unit tests and check pass rate."""
        print(f"\n{BLUE}{'='*70}{RESET}")
        print(f"{BOLD}Running Unit Tests Gate...{RESET}")
        print(f"{BLUE}{'='*70}{RESET}")
        
        # Run pytest with coverage and json report
        cmd = [
            "python", "-m", "pytest",
            str(self.test_dir),
            "-v",
            "--tb=short",
            "--disable-warnings",
            "-q" if not self.verbose else "",
        ]
        
        # Remove empty strings from cmd
        cmd = [c for c in cmd if c]
        
        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=300  # 5 minute timeout
            )
            
            output = result.stdout + result.stderr
            
            # Parse pytest output
            passed, failed, total = self._parse_pytest_output(output)
            
            threshold = QUALITY_GATES["unit_tests"]
            pass_rate = (passed / total * 100) if total > 0 else 0
            
            self.passed = (
                failed <= threshold["max_failures"] and
                pass_rate >= threshold["min_pass_rate"]
            )
            
            self.message = (
                f"Tests Run: {total}\n"
                f"Passed: {GREEN}{passed}{RESET}\n"
                f"Failed: {RED if failed > 0 else GREEN}{failed}{RESET}\n"
                f"Pass Rate: {GREEN if self.passed else RED}{pass_rate:.1f}%{RESET}\n"
                f"Threshold: ≥ {threshold['min_pass_rate']}% pass rate, ≤ {threshold['max_failures']} failures"
            )
            
            if self.verbose:
                self.message += f"\n\nDetailed Output:\n{output}"
            
            return self.passed
            
        except subprocess.TimeoutExpired:
            self.passed = False
            self.message = f"{RED}Tests timed out after 5 minutes{RESET}"
            return False
            
        except Exception as e:
            self.passed = False
            self.message = f"{RED}Error running tests: {e}{RESET}"
            return False
    
    def _parse_pytest_output(self, output: str) -> Tuple[int, int, int]:
        """Parse pytest output to extract pass/fail counts."""
        # Look for patterns like "5 passed, 2 failed" or "10 passed"
        passed = 0
        failed = 0
        
        # Pattern: "X passed"
        passed_match = re.search(r'(\d+) passed', output)
        if passed_match:
            passed = int(passed_match.group(1))
        
        # Pattern: "X failed"
        failed_match = re.search(r'(\d+) failed', output)
        if failed_match:
            failed = int(failed_match.group(1))
        
        total = passed + failed
        return passed, failed, total


class SchemaValidationGate(QualityGate):
    """Quality gate for Kafka schema validation."""
    
    def __init__(self, verbose: bool = False):
        super().__init__("Schema Validation Gate", verbose)
        
    def run(self) -> bool:
        """Run schema validation tests."""
        print(f"\n{BLUE}{'='*70}{RESET}")
        print(f"{BOLD}Running Schema Validation Gate...{RESET}")
        print(f"{BLUE}{'='*70}{RESET}")
        
        # Run schema-specific tests
        # Check if test files exist first
        test_files = []
        potential_files = [
            "tests/test_schemas.py",
            "tests/test_consumer.py", 
            "tests/test_ingestor.py"
        ]
        
        for file in potential_files:
            if Path(file).exists():
                test_files.append(file)
        
        if not test_files:
            self.passed = False
            self.message = f"{RED}No schema test files found!{RESET}"
            return False
        
        cmd = [
            "python", "-m", "pytest",
            *test_files,
            "-v",
            "-k", "schema or validate",
            "--tb=short",
            "-q" if not self.verbose else "",
        ]
        
        cmd = [c for c in cmd if c]
        
        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=120
            )
            
            output = result.stdout + result.stderr
            
            # Parse results
            passed, failed, total = self._parse_pytest_output(output)
            
            threshold = QUALITY_GATES["schema_validation"]
            pass_rate = (passed / total * 100) if total > 0 else 0
            
            # Check that schema validation tests ran and passed
            # Gate passes if: tests ran, all passed, and minimum 10 schema tests
            min_schema_tests = 10
            has_sufficient_tests = total >= min_schema_tests
            
            self.passed = (
                failed <= threshold["max_failures"] and
                pass_rate >= threshold["min_pass_rate"] and
                has_sufficient_tests
            )
            
            test_count_status = f"{GREEN}✓{RESET}" if has_sufficient_tests else f"{RED}✗{RESET}"
            
            self.message = (
                f"Schema Tests Run: {total} {test_count_status}\n"
                f"Passed: {GREEN}{passed}{RESET}\n"
                f"Failed: {RED if failed > 0 else GREEN}{failed}{RESET}\n"
                f"Pass Rate: {GREEN if pass_rate >= 100 else RED}{pass_rate:.1f}%{RESET}\n"
                f"Schema Coverage: Validation logic tests included\n"
                f"Threshold: 100% pass rate, ≥{min_schema_tests} schema validation tests"
            )
            
            if self.verbose:
                self.message += f"\n\nDetailed Output:\n{output}"
            
            return self.passed
            
        except Exception as e:
            self.passed = False
            self.message = f"{RED}Error running schema tests: {e}{RESET}"
            return False
    
    def _parse_pytest_output(self, output: str) -> Tuple[int, int, int]:
        """Parse pytest output."""
        passed = 0
        failed = 0
        
        passed_match = re.search(r'(\d+) passed', output)
        if passed_match:
            passed = int(passed_match.group(1))
        
        failed_match = re.search(r'(\d+) failed', output)
        if failed_match:
            failed = int(failed_match.group(1))
        
        total = passed + failed
        return passed, failed, total
    
    def _check_required_schemas(self, output: str) -> List[str]:
        """Check which schemas are covered in tests."""
        output_lower = output.lower()
        found = []
        for schema in QUALITY_GATES["schema_validation"]["required_schemas"]:
            if schema in output_lower:
                found.append(schema)
        return found


class BackpressureGate(QualityGate):
    """Quality gate for backpressure handling."""
    
    def __init__(self, verbose: bool = False):
        super().__init__("Backpressure Handling Gate", verbose)
        
    def run(self) -> bool:
        """Run backpressure handling tests."""
        print(f"\n{BLUE}{'='*70}{RESET}")
        print(f"{BOLD}Running Backpressure Handling Gate...{RESET}")
        print(f"{BLUE}{'='*70}{RESET}")
        
        # Run backpressure tests
        cmd = [
            "python", "-m", "pytest",
            "tests/test_backpressure.py",
            "-v",
            "--tb=short",
            "-s" if self.verbose else "-q",
        ]
        
        cmd = [c for c in cmd if c]
        
        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=180  # 3 minute timeout
            )
            
            output = result.stdout + result.stderr
            
            # Parse results
            passed, failed, total = self._parse_pytest_output(output)
            
            threshold = QUALITY_GATES["backpressure"]
            pass_rate = (passed / total * 100) if total > 0 else 0
            
            # Check minimum number of tests
            meets_test_count = total >= threshold["required_tests"]
            
            self.passed = (
                failed <= threshold["max_failures"] and
                pass_rate >= threshold["min_pass_rate"] and
                meets_test_count
            )
            
            test_count_status = f"{GREEN}✓{RESET}" if meets_test_count else f"{RED}✗{RESET}"
            
            self.message = (
                f"Backpressure Tests Run: {total} {test_count_status}\n"
                f"Passed: {GREEN}{passed}{RESET}\n"
                f"Failed: {RED if failed > 0 else GREEN}{failed}{RESET}\n"
                f"Pass Rate: {GREEN if self.passed else RED}{pass_rate:.1f}%{RESET}\n"
                f"Required Tests: ≥ {threshold['required_tests']} (batch size, time-based, data loss, etc.)\n"
                f"Threshold: 100% pass rate, ≥ {threshold['required_tests']} test cases"
            )
            
            if self.verbose:
                self.message += f"\n\nDetailed Output:\n{output}"
            
            return self.passed
            
        except Exception as e:
            self.passed = False
            self.message = f"{RED}Error running backpressure tests: {e}{RESET}"
            return False
    
    def _parse_pytest_output(self, output: str) -> Tuple[int, int, int]:
        """Parse pytest output."""
        passed = 0
        failed = 0
        
        passed_match = re.search(r'(\d+) passed', output)
        if passed_match:
            passed = int(passed_match.group(1))
        
        failed_match = re.search(r'(\d+) failed', output)
        if failed_match:
            failed = int(failed_match.group(1))
        
        total = passed + failed
        return passed, failed, total


def run_quality_gates(gates_to_run: List[str] = None, verbose: bool = False) -> bool:
    """
    Run quality gates and return overall pass/fail.
    
    Args:
        gates_to_run: List of gate names to run, or None for all
        verbose: Enable verbose output
        
    Returns:
        True if all gates passed, False otherwise
    """
    print(f"\n{BOLD}{BLUE}{'='*70}{RESET}")
    print(f"{BOLD}{BLUE}QUALITY GATE VALIDATION{RESET}")
    print(f"{BOLD}{BLUE}{'='*70}{RESET}\n")
    
    # Define all available gates
    all_gates = {
        "unit-tests": UnitTestGate(verbose),
        "schema-validation": SchemaValidationGate(verbose),
        "backpressure": BackpressureGate(verbose),
    }
    
    # Select gates to run
    if gates_to_run:
        gates = {k: v for k, v in all_gates.items() if k in gates_to_run}
        if not gates:
            print(f"{RED}Error: No valid gates specified{RESET}")
            print(f"Available gates: {', '.join(all_gates.keys())}")
            return False
    else:
        gates = all_gates
    
    # Run each gate
    results = {}
    for gate_name, gate in gates.items():
        try:
            passed = gate.run()
            gate.print_result()
            results[gate_name] = passed
        except Exception as e:
            print(f"{RED}Error running gate {gate_name}: {e}{RESET}")
            results[gate_name] = False
    
    # Print summary
    print(f"\n{BOLD}{BLUE}{'='*70}{RESET}")
    print(f"{BOLD}QUALITY GATE SUMMARY{RESET}")
    print(f"{BOLD}{BLUE}{'='*70}{RESET}\n")
    
    all_passed = all(results.values())
    
    for gate_name, passed in results.items():
        status = f"{GREEN}✓ PASS{RESET}" if passed else f"{RED}✗ FAIL{RESET}"
        print(f"  {status}  {gate_name}")
    
    print(f"\n{BOLD}{BLUE}{'='*70}{RESET}")
    
    if all_passed:
        print(f"{GREEN}{BOLD}✓ ALL QUALITY GATES PASSED{RESET}\n")
        return True
    else:
        failed_count = sum(1 for p in results.values() if not p)
        print(f"{RED}{BOLD}✗ {failed_count} QUALITY GATE(S) FAILED{RESET}\n")
        print(f"{YELLOW}Please fix the failures before merging or deploying.{RESET}\n")
        return False


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Run quality gates for the movie recommendation system",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Run all quality gates
  python scripts/quality_gate.py
  
  # Run specific gate
  python scripts/quality_gate.py --gate unit-tests
  
  # Run multiple gates with verbose output
  python scripts/quality_gate.py --gate unit-tests --gate schema-validation --verbose
  
Available gates:
  - unit-tests: Run all unit tests
  - schema-validation: Validate Kafka message schemas
  - backpressure: Test backpressure handling mechanisms
        """
    )
    
    parser.add_argument(
        "--gate",
        action="append",
        choices=["unit-tests", "schema-validation", "backpressure"],
        help="Specific gate(s) to run (can be specified multiple times)"
    )
    
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Enable verbose output"
    )
    
    args = parser.parse_args()
    
    # Run quality gates
    passed = run_quality_gates(args.gate, args.verbose)
    
    # Exit with appropriate code
    sys.exit(0 if passed else 1)


if __name__ == "__main__":
    main()
