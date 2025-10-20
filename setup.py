from setuptools import setup, find_packages

setup(
    name="movie-recs",
    version="0.1",
    packages=find_packages(),
    install_requires=[
        "fastapi",
        "uvicorn",
        "prometheus-client",
        "pydantic",
        "pandas",
        "pyarrow",
        "confluent-kafka",
        "python-dotenv",
        "scikit-learn",
        "numpy",
        "pytest",
        "fastavro"
    ]
)