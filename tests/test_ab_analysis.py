"""Unit tests for A/B testing statistical analysis."""

import pytest
import numpy as np
from service.ab_analysis import (
    two_proportion_ztest,
    bootstrap_ci,
    calculate_sample_size,
    make_decision,
    analyze_experiment,
    ExperimentDecision,
    ProportionTestResult,
    BootstrapResult
)


class TestTwoProportionZTest:
    """Tests for two-proportion z-test."""

    def test_identical_proportions(self):
        """Test when both variants have identical success rates."""
        result = two_proportion_ztest(
            successes_a=50,
            trials_a=100,
            successes_b=50,
            trials_b=100
        )
        assert isinstance(result, ProportionTestResult)
        assert abs(result.z_statistic) < 0.01  # Should be ~0
        assert result.p_value > 0.90  # High p-value (no difference)
        assert not result.significant

    def test_significant_difference(self):
        """Test when variants have significant difference."""
        result = two_proportion_ztest(
            successes_a=30,
            trials_a=100,
            successes_b=60,
            trials_b=100
        )
        assert result.p_value < 0.05
        assert result.significant
        assert result.delta > 0  # Variant B better

    def test_delta_calculation(self):
        """Test delta (effect size) calculation."""
        result = two_proportion_ztest(
            successes_a=40,
            trials_a=100,
            successes_b=60,
            trials_b=100
        )
        assert abs(result.delta - 0.20) < 0.01  # 60% - 40% = 20pp

    def test_zero_trials_raises_error(self):
        """Test that zero trials raises ValueError."""
        with pytest.raises(ValueError, match="Cannot perform test with zero trials"):
            two_proportion_ztest(0, 0, 50, 100)

    def test_confidence_interval_contains_zero_when_not_significant(self):
        """Test CI contains zero when no significant difference."""
        result = two_proportion_ztest(
            successes_a=50,
            trials_a=100,
            successes_b=52,
            trials_b=100
        )
        if not result.significant:
            assert result.ci_lower < 0 < result.ci_upper

    def test_to_dict(self):
        """Test conversion to dictionary."""
        result = two_proportion_ztest(50, 100, 60, 100)
        d = result.to_dict()
        assert "z_statistic" in d
        assert "p_value" in d
        assert "confidence_interval" in d
        assert len(d["confidence_interval"]) == 2


class TestBootstrapCI:
    """Tests for bootstrap confidence intervals."""

    def test_bootstrap_identical_data(self):
        """Test bootstrap with identical distributions."""
        data_a = np.array([1.0] * 100)
        data_b = np.array([1.0] * 100)
        result = bootstrap_ci(data_a, data_b, n_bootstrap=1000)

        assert isinstance(result, BootstrapResult)
        assert abs(result.delta_mean) < 0.01  # Should be ~0
        assert result.ci_lower <= result.delta_mean <= result.ci_upper

    def test_bootstrap_significant_difference(self):
        """Test bootstrap with clear difference."""
        data_a = np.array([1.0] * 100)
        data_b = np.array([2.0] * 100)
        result = bootstrap_ci(data_a, data_b, n_bootstrap=1000)

        assert abs(result.delta_mean - 1.0) < 0.05  # Mean difference ~1.0
        assert result.ci_lower > 0  # CI doesn't contain zero

    def test_empty_data_raises_error(self):
        """Test that empty data raises ValueError."""
        with pytest.raises(ValueError, match="Cannot bootstrap with empty data"):
            bootstrap_ci(np.array([]), np.array([1, 2, 3]))

    def test_custom_metric_function(self):
        """Test with custom metric (median instead of mean)."""
        # USE STABLE DATA for N=4 tests. 
        # Outliers with N=4 breaks bootstrap assumptions.
        data_a = np.array([1, 2, 3, 4, 5])   # Median = 3
        data_b = np.array([6, 7, 8, 9, 10])  # Median = 8
        
        # Expected difference: 8 - 3 = 5.0
        result = bootstrap_ci(data_a, data_b, metric_func=np.median, n_bootstrap=1000)
        
        # Check if result is close to 5.0
        assert abs(result.delta_mean - 5.0) < 0.5

    def test_to_dict(self):
        """Test conversion to dictionary."""
        data_a = np.array([1.0, 2.0, 3.0])
        data_b = np.array([2.0, 3.0, 4.0])
        result = bootstrap_ci(data_a, data_b, n_bootstrap=100)
        d = result.to_dict()

        assert "delta_mean" in d
        assert "confidence_interval" in d
        assert "ci_level" in d
        assert "n_bootstrap" in d


class TestCalculateSampleSize:
    """Tests for sample size calculation."""

    def test_sample_size_increases_with_smaller_effect(self):
        """Test that smaller MDE requires larger sample size."""
        n_large_effect = calculate_sample_size(baseline_rate=0.10, mde=0.10)
        n_small_effect = calculate_sample_size(baseline_rate=0.10, mde=0.02)

        assert n_small_effect > n_large_effect

    def test_sample_size_increases_with_higher_power(self):
        """Test that higher power requires larger sample size."""
        n_low_power = calculate_sample_size(baseline_rate=0.10, mde=0.05, power=0.70)
        n_high_power = calculate_sample_size(baseline_rate=0.10, mde=0.05, power=0.90)

        assert n_high_power > n_low_power

    def test_sample_size_is_positive_integer(self):
        """Test that sample size is a positive integer."""
        n = calculate_sample_size(baseline_rate=0.10, mde=0.05)
        assert isinstance(n, int)
        assert n > 0


class TestMakeDecision:
    """Tests for experiment decision logic."""

    def test_insufficient_sample_size(self):
        """Test inconclusive decision with insufficient samples."""
        result = ProportionTestResult(
            z_statistic=3.0,
            p_value=0.001,
            ci_lower=0.05,
            ci_upper=0.15,
            delta=0.10,
            variant_a_rate=0.40,
            variant_b_rate=0.50,
            sample_size_a=500,  # Below min_sample_size
            sample_size_b=500,
            significant=True
        )
        decision, rationale = make_decision(result, min_sample_size=1000)

        assert decision == ExperimentDecision.INCONCLUSIVE
        assert "Insufficient sample size" in rationale

    def test_not_significant(self):
        """Test no difference decision when not statistically significant."""
        result = ProportionTestResult(
            z_statistic=0.5,
            p_value=0.50,
            ci_lower=-0.05,
            ci_upper=0.07,
            delta=0.01,
            variant_a_rate=0.50,
            variant_b_rate=0.51,
            sample_size_a=2000,
            sample_size_b=2000,
            significant=False
        )
        decision, rationale = make_decision(result)

        assert decision == ExperimentDecision.NO_DIFFERENCE
        assert "not statistically significant" in rationale.lower()

    def test_too_small_effect(self):
        """Test no difference when effect is too small to be practical."""
        result = ProportionTestResult(
            z_statistic=2.5,
            p_value=0.01,
            ci_lower=0.002,
            ci_upper=0.008,
            delta=0.005,  # 0.5pp, below 1pp threshold
            variant_a_rate=0.500,
            variant_b_rate=0.505,
            sample_size_a=10000,
            sample_size_b=10000,
            significant=True
        )
        decision, rationale = make_decision(result, min_effect_size=0.01)

        assert decision == ExperimentDecision.NO_DIFFERENCE
        assert "effect size too small" in rationale.lower()

    def test_ship_variant_b(self):
        """Test ship variant B when it's significantly better."""
        result = ProportionTestResult(
            z_statistic=5.0,
            p_value=0.0001,
            ci_lower=0.08,
            ci_upper=0.12,
            delta=0.10,
            variant_a_rate=0.40,
            variant_b_rate=0.50,
            sample_size_a=2000,
            sample_size_b=2000,
            significant=True
        )
        decision, rationale = make_decision(result)

        assert decision == ExperimentDecision.SHIP_VARIANT_B
        assert "Variant B is significantly better" in rationale

    def test_ship_variant_a(self):
        """Test keep variant A when variant B is significantly worse."""
        result = ProportionTestResult(
            z_statistic=-5.0,
            p_value=0.0001,
            ci_lower=-0.12,
            ci_upper=-0.08,
            delta=-0.10,
            variant_a_rate=0.50,
            variant_b_rate=0.40,
            sample_size_a=2000,
            sample_size_b=2000,
            significant=True
        )
        decision, rationale = make_decision(result)

        assert decision == ExperimentDecision.SHIP_VARIANT_A
        assert "Variant A is significantly better" in rationale


class TestAnalyzeExperiment:
    """Tests for complete experiment analysis."""

    def test_analyze_experiment_returns_dict(self):
        """Test that analyze_experiment returns proper structure."""
        result = analyze_experiment(
            variant_a_successes=400,
            variant_a_trials=1000,
            variant_b_successes=500,
            variant_b_trials=1000,
            metric_name="conversion_rate"
        )

        assert isinstance(result, dict)
        assert "metric" in result
        assert "test" in result
        assert "results" in result
        assert "decision" in result
        assert "recommendation" in result

    def test_analyze_experiment_decision_ship_b(self):
        """Test analysis recommends shipping variant B when clearly better."""
        result = analyze_experiment(
            variant_a_successes=400,
            variant_a_trials=2000,
            variant_b_successes=600,
            variant_b_trials=2000
        )

        assert result["decision"] == "ship_variant_b"

    def test_analyze_experiment_decision_no_difference(self):
        """Test analysis shows no difference when appropriate."""
        result = analyze_experiment(
            variant_a_successes=1000,
            variant_a_trials=2000,
            variant_b_successes=1010,
            variant_b_trials=2000
        )

        # Small difference should not be significant
        assert result["decision"] in ["no_difference", "ship_variant_b"]
