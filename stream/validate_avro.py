import pathlib, fastavro, json

HERE = pathlib.Path(__file__).resolve().parent
SCHEMA_DIR = HERE / "schemas"

def load(name):
    path = SCHEMA_DIR / f"{name}.avsc"
    if not path.exists():
        raise FileNotFoundError(f"Missing schema file: {path}")
    return fastavro.schema.load_schema(path)

SCHEMAS = {
    "watch": load("watch"),
    "rate": load("rate"),
    "reco_response": load("reco_response"),
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
