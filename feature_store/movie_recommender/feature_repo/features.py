"""
Feature definitions for Movie Recommender System. This module defines features for users and 
movies that will be used both for training and serving recommendations, ensuring consistency 
and preventing training-serving skew.
"""

from datetime import timedelta
from feast import Entity, Feature, FeatureView, FileSource, ValueType
from feast.types import Float32, Int64, String

# =============================================================================
# Entities
# =============================================================================

# User entity - represents individual users
user = Entity(
    name="user_id",
    description="Unique identifier for a user",
    value_type=ValueType.INT64
)

# Movie entity - represents individual movies
movie = Entity(
    name="movie_id",
    description="Unique identifier for a movie",
    value_type=ValueType.INT64
)

# =============================================================================
# Data Sources
# =============================================================================

# User features source 
user_features_source = FileSource(
    path="../../../data/user_features.parquet",
    timestamp_field="event_timestamp",
)

# Movie features source
movie_features_source = FileSource(
    path="../../../data/movie_features.parquet",
    timestamp_field="event_timestamp",
)

# =============================================================================
# Feature Views
# =============================================================================

user_features_view = FeatureView(
    name="user_features",
    entities=[user],
    ttl=timedelta(days=365),  # Features valid for 1 year
    schema=[
        Feature(name="avg_rating", dtype=Float32, description="User's average rating"),
        Feature(name="num_ratings", dtype=Int64, description="Total number of ratings by user"),
        Feature(name="rating_std", dtype=Float32, description="Standard deviation of user's ratings"),
        Feature(name="favorite_genre", dtype=String, description="User's most-watched genre"),
    ],
    source=user_features_source,
    online=True,
    tags={"team": "ml-ops", "use_case": "recommendations"},
)

movie_features_view = FeatureView(
    name="movie_features",
    entities=[movie],
    ttl=timedelta(days=90),  # Features valid for 90 days (movies change popularity)
    schema=[
        Feature(name="avg_rating", dtype=Float32, description="Movie's average rating"),
        Feature(name="num_ratings", dtype=Int64, description="Total number of ratings for movie"),
        Feature(name="rating_std", dtype=Float32, description="Standard deviation of movie's ratings"),
        Feature(name="popularity_score", dtype=Float32, description="Popularity score (normalized)"),
        Feature(name="genre", dtype=String, description="Primary genre of the movie"),
    ],
    source=movie_features_source,
    online=True,
    tags={"team": "ml-ops", "use_case": "recommendations"},
)
