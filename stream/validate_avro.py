import json, fastavro, pathlib
from fastavro.validation import validate_many

ROOT = pathlib.Path(__file__).resolve().parents[2]
SCHEMA_DIR = ROOT / "stream/schemas"

SCHEMAS = {
    "watch": fastavro.schema.load_schema(SCHEMA_DIR / "watch.avsc"),
    "rate": fastavro.schema.load_schema(SCHEMA_DIR / "rate.avsc"),
    "reco_response": fastavro.schema.load_schema(SCHEMA_DIR / "reco_response.avsc"),
}

def validate_record(record, schema_name: str) -> bool:
    """Validate a single JSON record against an Avro schema."""
    schema = SCHEMAS[schema_name]
    try:
        fastavro.validation.validate(record, schema)
        return True
    except fastavro.validation.ValidationError as e:
        print(f"[AVRO] Validation failed for {schema_name}: {e}")
        return False

def validate_batch(records, schema_name: str) -> bool:
    schema = SCHEMAS[schema_name]
    return validate_many(records, schema)
