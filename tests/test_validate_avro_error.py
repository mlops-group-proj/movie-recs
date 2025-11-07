import pytest
from stream.validate_avro import validate_batch as validate_avro

def test_invalid_schema(tmp_path):
    bad_schema = tmp_path / "bad_schema.avsc"
    bad_schema.write_text('{"type": "record", "name": "Bad", "fields": [{"name": "x", "type": "unknown"}]}')
    with pytest.raises(Exception):
        validate_avro(bad_schema)
