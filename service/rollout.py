"""Environment-based rollout strategy for model deployments.

Supports gradual rollout strategies:
- canary: Small percentage of traffic gets new version
- blue-green: Full switch between two versions
- shadow: Parallel testing without affecting production responses
"""

from __future__ import annotations

import os
import random
from enum import Enum
from typing import Dict, Optional


class RolloutStrategy(str, Enum):
    """Rollout deployment strategies."""
    FIXED = "fixed"          # All traffic to specified version
    CANARY = "canary"        # Gradual rollout based on percentage
    AB_TEST = "ab_test"      # A/B testing based on user_id
    SHADOW = "shadow"        # Shadow mode (log only, don't serve)


class RolloutConfig:
    """Configuration for environment-based model rollout."""

    def __init__(
        self,
        strategy: RolloutStrategy = RolloutStrategy.FIXED,
        primary_version: str = "v0.3",
        canary_version: Optional[str] = None,
        canary_percentage: float = 0.0,
        environment: str = "production",
    ):
        self.strategy = strategy
        self.primary_version = primary_version
        self.canary_version = canary_version
        self.canary_percentage = max(0.0, min(100.0, canary_percentage))
        self.environment = environment

    @classmethod
    def from_env(cls) -> RolloutConfig:
        """Load rollout config from environment variables."""
        strategy_str = os.getenv("ROLLOUT_STRATEGY", "fixed").lower()
        strategy = RolloutStrategy(strategy_str) if strategy_str in RolloutStrategy.__members__.values() else RolloutStrategy.FIXED

        return cls(
            strategy=strategy,
            primary_version=os.getenv("MODEL_VERSION", "v0.3"),
            canary_version=os.getenv("CANARY_VERSION"),
            canary_percentage=float(os.getenv("CANARY_PERCENTAGE", "0")),
            environment=os.getenv("ENVIRONMENT", "production"),
        )

    def select_version(self, user_id: int) -> str:
        """Select model version based on rollout strategy."""
        if self.strategy == RolloutStrategy.FIXED:
            return self.primary_version

        elif self.strategy == RolloutStrategy.CANARY:
            if not self.canary_version:
                return self.primary_version
            # Deterministic based on user_id for consistency
            if (user_id % 100) < self.canary_percentage:
                return self.canary_version
            return self.primary_version

        elif self.strategy == RolloutStrategy.AB_TEST:
            if not self.canary_version:
                return self.primary_version
            # Split based on user_id parity: even=primary (A), odd=canary (B)
            return self.primary_version if (user_id % 2 == 0) else self.canary_version

        elif self.strategy == RolloutStrategy.SHADOW:
            # Shadow mode: always return primary, log canary predictions separately
            return self.primary_version

        return self.primary_version

    def to_dict(self) -> Dict:
        """Export config as dictionary."""
        return {
            "strategy": self.strategy.value,
            "primary_version": self.primary_version,
            "canary_version": self.canary_version,
            "canary_percentage": self.canary_percentage,
            "environment": self.environment,
        }
