# AWS Setup Guide (Minimal Cost)

This guide sets up the cheapest possible AWS infrastructure for:
- S3 storage for training data and model artifacts
- ECR for Docker container images
- (Optional) ECS/EC2 for running containers

## Estimated Costs

| Service | Usage | Cost |
|---------|-------|------|
| S3 | 10GB storage | ~$0.23/month |
| ECR | 5GB images | ~$0.50/month |
| **Total** | | **< $1/month** |

Note: AWS Free Tier includes 5GB S3 and 500MB ECR for 12 months.

---

## Step 1: Create AWS Account & IAM User

### 1.1 Create IAM User for CI/CD

```bash
# Install AWS CLI if not already installed
brew install awscli  # macOS
# or: pip install awscli

# Configure with root/admin credentials first
aws configure
```

### 1.2 Create Programmatic Access User

Go to AWS Console → IAM → Users → Create User:

1. User name: `mlops-ci-cd`
2. Select "Programmatic access"
3. Attach policies directly:
   - `AmazonS3FullAccess`
   - `AmazonEC2ContainerRegistryFullAccess`
4. Create user and **save the credentials**

---

## Step 2: Create S3 Bucket

```bash
# Set your bucket name (must be globally unique)
BUCKET_NAME="mlops-movie-recs-$(whoami)"

# Create bucket
aws s3 mb s3://$BUCKET_NAME --region us-east-1

# Enable versioning (optional, for model versioning)
aws s3api put-bucket-versioning \
  --bucket $BUCKET_NAME \
  --versioning-configuration Status=Enabled

# Set lifecycle policy to delete old versions after 30 days (cost savings)
cat > /tmp/lifecycle.json << 'EOF'
{
  "Rules": [
    {
      "ID": "DeleteOldVersions",
      "Status": "Enabled",
      "NoncurrentVersionExpiration": {
        "NoncurrentDays": 30
      },
      "Filter": {
        "Prefix": ""
      }
    }
  ]
}
EOF

aws s3api put-bucket-lifecycle-configuration \
  --bucket $BUCKET_NAME \
  --lifecycle-configuration file:///tmp/lifecycle.json

echo "Created bucket: $BUCKET_NAME"
```

### S3 Bucket Structure

```
s3://mlops-movie-recs-xxx/
├── data/
│   ├── raw/                    # Raw MovieLens data
│   ├── processed/              # Processed training data
│   └── snapshots/              # Kafka event snapshots
├── models/
│   ├── v0.1/
│   ├── v0.2/
│   └── current -> v0.2        # Symlink to current model
└── artifacts/
    └── metrics/                # Training metrics, evaluation results
```

---

## Step 3: Create ECR Repository

```bash
# Create repository for API image
aws ecr create-repository \
  --repository-name movie-recommender-api \
  --region us-east-1

# Create repository for trainer image (optional)
aws ecr create-repository \
  --repository-name movie-recommender-trainer \
  --region us-east-1

# Get your ECR registry URL
AWS_ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)
ECR_REGISTRY="${AWS_ACCOUNT_ID}.dkr.ecr.us-east-1.amazonaws.com"

echo "ECR Registry: $ECR_REGISTRY"
```

### Set ECR Lifecycle Policy (Cost Savings)

Keep only the last 5 images to save storage costs:

```bash
cat > /tmp/ecr-lifecycle.json << 'EOF'
{
  "rules": [
    {
      "rulePriority": 1,
      "description": "Keep only last 5 images",
      "selection": {
        "tagStatus": "any",
        "countType": "imageCountMoreThan",
        "countNumber": 5
      },
      "action": {
        "type": "expire"
      }
    }
  ]
}
EOF

aws ecr put-lifecycle-policy \
  --repository-name movie-recommender-api \
  --lifecycle-policy-text file:///tmp/ecr-lifecycle.json

aws ecr put-lifecycle-policy \
  --repository-name movie-recommender-trainer \
  --lifecycle-policy-text file:///tmp/ecr-lifecycle.json
```

---

## Step 4: GitHub Secrets

Add these secrets to your GitHub repository:

| Secret Name | Value |
|-------------|-------|
| `AWS_ACCESS_KEY_ID` | From IAM user creation |
| `AWS_SECRET_ACCESS_KEY` | From IAM user creation |
| `AWS_REGION` | `us-east-1` |
| `AWS_ACCOUNT_ID` | Your 12-digit account ID |
| `S3_BUCKET` | Your bucket name |

### How to Add Secrets

1. Go to your GitHub repo → Settings → Secrets and variables → Actions
2. Click "New repository secret"
3. Add each secret

---

## Step 5: Environment Variables

Create a `.env.aws` file (don't commit this!):

```bash
# AWS Credentials
AWS_ACCESS_KEY_ID=your_access_key
AWS_SECRET_ACCESS_KEY=your_secret_key
AWS_REGION=us-east-1

# S3 Configuration
S3_BUCKET=mlops-movie-recs-xxx
S3_PREFIX=snapshots
USE_S3=true

# ECR Configuration
ECR_REGISTRY=123456789012.dkr.ecr.us-east-1.amazonaws.com
```

---

## Step 6: Push Docker Image to ECR

```bash
# Login to ECR
aws ecr get-login-password --region us-east-1 | \
  docker login --username AWS --password-stdin $ECR_REGISTRY

# Build and tag image
docker build -t movie-recommender-api -f docker/recommender.Dockerfile .
docker tag movie-recommender-api:latest $ECR_REGISTRY/movie-recommender-api:latest

# Push to ECR
docker push $ECR_REGISTRY/movie-recommender-api:latest
```

---

## Step 7: Test S3 Integration

```bash
# Upload test file
echo "test" | aws s3 cp - s3://$BUCKET_NAME/test.txt

# Verify
aws s3 ls s3://$BUCKET_NAME/

# Clean up
aws s3 rm s3://$BUCKET_NAME/test.txt
```

---

## GitHub Actions Workflow

Example workflow for building and pushing to ECR:

```yaml
# .github/workflows/build-push-ecr.yml
name: Build and Push to ECR

on:
  push:
    branches: [main]
    paths:
      - 'service/**'
      - 'recommender/**'
      - 'docker/**'

jobs:
  build:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - name: Configure AWS credentials
        uses: aws-actions/configure-aws-credentials@v4
        with:
          aws-access-key-id: ${{ secrets.AWS_ACCESS_KEY_ID }}
          aws-secret-access-key: ${{ secrets.AWS_SECRET_ACCESS_KEY }}
          aws-region: ${{ secrets.AWS_REGION }}

      - name: Login to Amazon ECR
        id: login-ecr
        uses: aws-actions/amazon-ecr-login@v2

      - name: Build, tag, and push image to Amazon ECR
        env:
          ECR_REGISTRY: ${{ steps.login-ecr.outputs.registry }}
          ECR_REPOSITORY: movie-recommender-api
          IMAGE_TAG: ${{ github.sha }}
        run: |
          docker build -t $ECR_REGISTRY/$ECR_REPOSITORY:$IMAGE_TAG -f docker/recommender.Dockerfile .
          docker push $ECR_REGISTRY/$ECR_REPOSITORY:$IMAGE_TAG
          docker tag $ECR_REGISTRY/$ECR_REPOSITORY:$IMAGE_TAG $ECR_REGISTRY/$ECR_REPOSITORY:latest
          docker push $ECR_REGISTRY/$ECR_REPOSITORY:latest
```

---

## Cost Optimization Tips

1. **Use S3 Intelligent-Tiering** for data accessed less frequently
2. **Set ECR lifecycle policies** to auto-delete old images
3. **Use S3 lifecycle rules** to expire old data
4. **Stay in one region** (us-east-1 is cheapest)
5. **Don't use NAT Gateway** if possible (expensive!)
6. **Use Spot instances** if running EC2/ECS

---

## Cleanup (Delete Everything)

```bash
# Empty and delete S3 bucket
aws s3 rm s3://$BUCKET_NAME --recursive
aws s3 rb s3://$BUCKET_NAME

# Delete ECR repositories
aws ecr delete-repository --repository-name movie-recommender-api --force
aws ecr delete-repository --repository-name movie-recommender-trainer --force

# Delete IAM user (from console or CLI)
aws iam delete-access-key --user-name mlops-ci-cd --access-key-id YOUR_ACCESS_KEY_ID
aws iam detach-user-policy --user-name mlops-ci-cd --policy-arn arn:aws:iam::aws:policy/AmazonS3FullAccess
aws iam detach-user-policy --user-name mlops-ci-cd --policy-arn arn:aws:iam::aws:policy/AmazonEC2ContainerRegistryFullAccess
aws iam delete-user --user-name mlops-ci-cd
```
