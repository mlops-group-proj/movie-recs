"""Statistical testing and analysis for A/B experiments.

Provides tools for:
- Two-proportion z-test for conversion rate comparison
- Bootstrap confidence intervals for metric deltas
- Sample size calculation (power analysis)
- Experiment decision logic
"""

from __future__ import annotations

import math
import numpy as np
from typing import Dict, Tuple, Optional
from dataclasses import dataclass
from enum import Enum


class ExperimentDecision(str, Enum):
    """Experiment decision outcomes."""
    SHIP_VARIANT_A = "ship_variant_a"  # Variant A is significantly better
    SHIP_VARIANT_B = "ship_variant_b"  # Variant B is significantly better
    INCONCLUSIVE = "inconclusive"      # Not enough evidence
    NO_DIFFERENCE = "no_difference"    # No statistically significant difference


@dataclass
class ProportionTestResult:
    """Results from a two-proportion z-test."""
    z_statistic: float
    p_value: float
    ci_lower: float
    ci_upper: float
    delta: float  # Variant B - Variant A
    variant_a_rate: float
    variant_b_rate: float
    sample_size_a: int
    sample_size_b: int
    significant: bool  # p < 0.05

    def to_dict(self) -> Dict:
        return {
            "z_statistic": self.z_statistic,
            "p_value": self.p_value,
            "confidence_interval": [self.ci_lower, self.ci_upper],
            "delta": self.delta,
            "variant_a_rate": self.variant_a_rate,
            "variant_b_rate": self.variant_b_rate,
            "sample_size_a": self.sample_size_a,
            "sample_size_b": self.sample_size_b,
            "significant": self.significant,
        }


@dataclass
class BootstrapResult:
    """Results from bootstrap confidence interval estimation."""
    delta_mean: float
    ci_lower: float
    ci_upper: float
    ci_level: float  # e.g., 0.95
    n_bootstrap: int

    def to_dict(self) -> Dict:
        return {
            "delta_mean": self.delta_mean,
            "confidence_interval": [self.ci_lower, self.ci_upper],
            "ci_level": self.ci_level,
            "n_bootstrap": self.n_bootstrap,
        }


def two_proportion_ztest(
    successes_a: int,
    trials_a: int,
    successes_b: int,
    trials_b: int,
    alpha: float = 0.05
) -> ProportionTestResult:
    """Perform a two-proportion z-test.

    Tests whether the proportions in two groups differ significantly.
    H0: p_a = p_b
    H1: p_a ≠ p_b

    Args:
        successes_a: Number of successes in variant A
        trials_a: Total trials in variant A
        successes_b: Number of successes in variant B
        trials_b: Total trials in variant B
        alpha: Significance level (default: 0.05 for 95% CI)

    Returns:
        ProportionTestResult with z-statistic, p-value, and CIs
    """
    if trials_a == 0 or trials_b == 0:
        raise ValueError("Cannot perform test with zero trials")

    # Calculate proportions
    p_a = successes_a / trials_a
    p_b = successes_b / trials_b
    delta = p_b - p_a

    # Pooled proportion for null hypothesis
    p_pooled = (successes_a + successes_b) / (trials_a + trials_b)

    # Standard error under null hypothesis
    se_null = math.sqrt(p_pooled * (1 - p_pooled) * (1/trials_a + 1/trials_b))

    # Z-statistic
    z_stat = delta / se_null if se_null > 0 else 0.0

    # Two-tailed p-value (using normal approximation)
    from scipy import stats
    p_value = 2 * (1 - stats.norm.cdf(abs(z_stat)))

    # Confidence interval for difference (using unpooled SE)
    se_diff = math.sqrt((p_a * (1 - p_a) / trials_a) + (p_b * (1 - p_b) / trials_b))
    z_critical = stats.norm.ppf(1 - alpha/2)  # Two-tailed
    ci_lower = delta - z_critical * se_diff
    ci_upper = delta + z_critical * se_diff

    return ProportionTestResult(
        z_statistic=z_stat,
        p_value=p_value,
        ci_lower=ci_lower,
        ci_upper=ci_upper,
        delta=delta,
        variant_a_rate=p_a,
        variant_b_rate=p_b,
        sample_size_a=trials_a,
        sample_size_b=trials_b,
        significant=(p_value < alpha)
    )


def bootstrap_ci(
    data_a: np.ndarray,
    data_b: np.ndarray,
    metric_func=np.mean,
    n_bootstrap: int = 10000,
    ci_level: float = 0.95
) -> BootstrapResult:
    """Bootstrap confidence interval for difference in metrics.

    Args:
        data_a: Data samples from variant A
        data_b: Data samples from variant B
        metric_func: Function to compute metric (default: mean)
        n_bootstrap: Number of bootstrap samples
        ci_level: Confidence level (e.g., 0.95 for 95% CI)

    Returns:
        BootstrapResult with delta and confidence interval
    """
    if len(data_a) == 0 or len(data_b) == 0:
        raise ValueError("Cannot bootstrap with empty data")

    deltas = []
    rng = np.random.RandomState(42)  # Reproducible

    for _ in range(n_bootstrap):
        # Resample with replacement
        sample_a = rng.choice(data_a, size=len(data_a), replace=True)
        sample_b = rng.choice(data_b, size=len(data_b), replace=True)

        # Compute metric for each sample
        metric_a = metric_func(sample_a)
        metric_b = metric_func(sample_b)
        deltas.append(metric_b - metric_a)

    deltas = np.array(deltas)
    delta_mean = np.mean(deltas)

    # Percentile method for CI
    alpha = 1 - ci_level
    ci_lower = np.percentile(deltas, 100 * alpha / 2)
    ci_upper = np.percentile(deltas, 100 * (1 - alpha / 2))

    return BootstrapResult(
        delta_mean=delta_mean,
        ci_lower=ci_lower,
        ci_upper=ci_upper,
        ci_level=ci_level,
        n_bootstrap=n_bootstrap
    )


def calculate_sample_size(
    baseline_rate: float,
    mde: float,  # Minimum detectable effect (absolute, e.g., 0.05 for 5 percentage points)
    alpha: float = 0.05,
    power: float = 0.80
) -> int:
    """Calculate required sample size per variant for a proportion test.

    Args:
        baseline_rate: Expected baseline conversion rate (e.g., 0.10 for 10%)
        mde: Minimum detectable effect (absolute difference, e.g., 0.02 for 2pp)
        alpha: Significance level (Type I error rate)
        power: Statistical power (1 - Type II error rate)

    Returns:
        Required sample size per variant
    """
    from scipy import stats

    # Z-scores for alpha and power
    z_alpha = stats.norm.ppf(1 - alpha / 2)  # Two-tailed
    z_beta = stats.norm.ppf(power)

    # Expected rates
    p1 = baseline_rate
    p2 = baseline_rate + mde
    p_avg = (p1 + p2) / 2

    # Sample size formula (Fleiss, 1981)
    numerator = (z_alpha + z_beta) ** 2 * 2 * p_avg * (1 - p_avg)
    denominator = mde ** 2

    n = math.ceil(numerator / denominator)
    return n


def make_decision(
    test_result: ProportionTestResult,
    min_effect_size: float = 0.01,  # 1 percentage point minimum
    min_sample_size: int = 1000
) -> Tuple[ExperimentDecision, str]:
    """Make a ship/no-ship decision based on statistical test results.

    Decision logic:
    1. Check minimum sample size requirement
    2. Check statistical significance (p < 0.05)
    3. Check practical significance (|effect| > min_effect_size)
    4. Recommend based on direction and magnitude

    Args:
        test_result: Results from two_proportion_ztest
        min_effect_size: Minimum practical effect size (absolute)
        min_sample_size: Minimum sample size per variant

    Returns:
        (decision, rationale) tuple
    """
    # Check sample size
    if test_result.sample_size_a < min_sample_size or test_result.sample_size_b < min_sample_size:
        return (
            ExperimentDecision.INCONCLUSIVE,
            f"Insufficient sample size (need ≥{min_sample_size} per variant). Continue experiment."
        )

    # Check statistical significance
    if not test_result.significant:
        return (
            ExperimentDecision.NO_DIFFERENCE,
            f"No statistically significant difference (p={test_result.p_value:.4f}). "
            f"Safe to ship either variant or choose based on other criteria."
        )

    # Check practical significance
    if abs(test_result.delta) < min_effect_size:
        return (
            ExperimentDecision.NO_DIFFERENCE,
            f"Statistically significant but effect size too small ({test_result.delta:.4f} < {min_effect_size}). "
            f"No practical difference."
        )

    # Significant and practically meaningful
    if test_result.delta > 0:
        return (
            ExperimentDecision.SHIP_VARIANT_B,
            f"Variant B is significantly better (+{test_result.delta:.4f}, p={test_result.p_value:.4f}). Recommend shipping Variant B."
        )
    else:
        return (
            ExperimentDecision.SHIP_VARIANT_A,
            f"Variant A is significantly better ({test_result.delta:.4f}, p={test_result.p_value:.4f}). Keep Variant A."
        )


def analyze_experiment(
    variant_a_successes: int,
    variant_a_trials: int,
    variant_b_successes: int,
    variant_b_trials: int,
    metric_name: str = "conversion_rate"
) -> Dict:
    """Complete experiment analysis with test results and recommendation.

    Args:
        variant_a_successes: Successes in variant A
        variant_a_trials: Total trials in variant A
        variant_b_successes: Successes in variant B
        variant_b_trials: Total trials in variant B
        metric_name: Name of the metric being tested

    Returns:
        Dictionary with test results, decision, and recommendation
    """
    # Run statistical test
    test_result = two_proportion_ztest(
        variant_a_successes,
        variant_a_trials,
        variant_b_successes,
        variant_b_trials
    )

    # Make decision
    decision, rationale = make_decision(test_result)

    return {
        "metric": metric_name,
        "test": "two_proportion_z_test",
        "results": test_result.to_dict(),
        "decision": decision.value,
        "recommendation": rationale,
    }
