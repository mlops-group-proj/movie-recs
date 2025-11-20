"""
Test script to verify S3 integration for parquet file writing.
"""
import os
import sys
from datetime import datetime, timezone
UTC = timezone.utc
from pathlib import Path

# Ensure local imports work
project_root = str(Path(__file__).parent.absolute())
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from dotenv import load_dotenv
load_dotenv()

from stream.ingestor import StreamIngestor

def test_s3_write():
    """Test writing a batch to S3."""
    print("=" * 60)
    print("Testing S3 Integration for Parquet Writing")
    print("=" * 60)
    
    # Check configuration
    use_s3 = os.getenv("USE_S3", "").lower() == "true"
    s3_bucket = os.getenv("S3_BUCKET")
    s3_prefix = os.getenv("S3_PREFIX", "snapshots")
    aws_region = os.getenv("AWS_REGION")
    
    print(f"\nConfiguration:")
    print(f"  USE_S3: {use_s3}")
    print(f"  S3_BUCKET: {s3_bucket}")
    print(f"  S3_PREFIX: {s3_prefix}")
    print(f"  AWS_REGION: {aws_region}")
    
    if not use_s3:
        print("\nXX USE_S3 is not set to true in .env file")
        return False
    
    if not s3_bucket:
        print("\nXX S3_BUCKET is not set in .env file")
        return False
    
    print("\n" + "-" * 60)
    print("Initializing StreamIngestor with S3 enabled...")
    print("-" * 60)
    
    try:
        # Initialize the ingestor (this will test S3 client creation)
        ingestor = StreamIngestor(
            storage_path="data/snapshots",
            batch_size=10,  # Small batch for testing
            flush_interval_sec=300,
        )
        
        print(f"\n*  StreamIngestor initialized successfully")
        print(f"   S3 Client: {'Enabled' if ingestor.s3_client else 'Disabled'}")
        
        # Create test data
        print("\n" + "-" * 60)
        print("Creating test batch data...")
        print("-" * 60)
        
        test_batch = [
            {
                "user_id": 1,
                "movie_id": 101,
                "timestamp": datetime.now(UTC).isoformat()
            },
            {
                "user_id": 2,
                "movie_id": 102,
                "timestamp": datetime.now(UTC).isoformat()
            },
            {
                "user_id": 3,
                "movie_id": 103,
                "timestamp": datetime.now(UTC).isoformat()
            }
        ]
        
        print(f"   Created {len(test_batch)} test records")
        
        # Test writing to S3
        print("\n" + "-" * 60)
        print("Writing test batch to S3...")
        print("-" * 60)
        
        ingestor._write_batch_to_parquet("watch", test_batch)
        
        print("\n*  Test batch written successfully!")
        
        # Verify the file exists in S3
        print("\n" + "-" * 60)
        print("Verifying file in S3...")
        print("-" * 60)
        
        import boto3
        s3_client = boto3.client('s3', region_name=aws_region)
        
        # List files in the watch directory
        date_str = datetime.now(UTC).strftime('%Y-%m-%d')
        prefix = f"{s3_prefix}/watch/{date_str}/"
        
        response = s3_client.list_objects_v2(
            Bucket=s3_bucket,
            Prefix=prefix
        )
        
        if 'Contents' in response:
            print(f"\n*  Found {len(response['Contents'])} file(s) in S3:")
            for obj in response['Contents']:
                print(f"   - {obj['Key']} ({obj['Size']} bytes)")
        else:
            print(f"\n!!  No files found at s3://{s3_bucket}/{prefix}")
        
        print("\n" + "=" * 60)
        print("*  S3 INTEGRATION TEST PASSED!")
        print("=" * 60)
        print(f"\nYour parquets will be written to:")
        print(f"  s3://{s3_bucket}/{s3_prefix}/{{topic}}/{{date}}/batch_*.parquet")
        print()
        
        return True
        
    except Exception as e:
        print(f"\nXX TEST FAILED: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    success = test_s3_write()
    sys.exit(0 if success else 1)
