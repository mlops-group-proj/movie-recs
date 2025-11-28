#!/bin/bash
# AWS Setup Script for MLOps Movie Recommender
# Run this after creating an AWS account and configuring AWS CLI

set -e

# Configuration
BUCKET_NAME="${S3_BUCKET:-mlops-movie-recs-$(whoami)}"
REGION="${AWS_REGION:-us-east-1}"
IAM_USER="mlops-ci-cd"

echo "========================================"
echo "AWS Setup for Movie Recommender MLOps"
echo "========================================"
echo "Region: $REGION"
echo "Bucket: $BUCKET_NAME"
echo ""

# Check AWS CLI is configured
if ! aws sts get-caller-identity &>/dev/null; then
    echo "ERROR: AWS CLI not configured. Run 'aws configure' first."
    exit 1
fi

AWS_ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)
echo "Account ID: $AWS_ACCOUNT_ID"
echo ""

# 1. Create S3 Bucket
echo "1. Creating S3 bucket..."
if aws s3 ls "s3://$BUCKET_NAME" 2>&1 | grep -q 'NoSuchBucket'; then
    aws s3 mb "s3://$BUCKET_NAME" --region "$REGION"
    echo "   Created: s3://$BUCKET_NAME"
else
    echo "   Bucket already exists or name taken"
fi

# 2. Create ECR Repository
echo "2. Creating ECR repository..."
if ! aws ecr describe-repositories --repository-names movie-recommender-api --region "$REGION" &>/dev/null; then
    aws ecr create-repository \
        --repository-name movie-recommender-api \
        --region "$REGION" \
        --image-scanning-configuration scanOnPush=false
    echo "   Created: movie-recommender-api"
else
    echo "   Repository already exists"
fi

# 3. Set ECR lifecycle policy (keep only 5 images)
echo "3. Setting ECR lifecycle policy..."
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
    --lifecycle-policy-text file:///tmp/ecr-lifecycle.json \
    --region "$REGION" &>/dev/null
echo "   Lifecycle policy set (keeps last 5 images)"

# 4. Create IAM user for CI/CD (if not exists)
echo "4. Checking IAM user..."
if ! aws iam get-user --user-name "$IAM_USER" &>/dev/null; then
    echo "   Creating IAM user: $IAM_USER"
    aws iam create-user --user-name "$IAM_USER"

    # Attach policies
    aws iam attach-user-policy --user-name "$IAM_USER" \
        --policy-arn arn:aws:iam::aws:policy/AmazonS3FullAccess
    aws iam attach-user-policy --user-name "$IAM_USER" \
        --policy-arn arn:aws:iam::aws:policy/AmazonEC2ContainerRegistryFullAccess

    # Create access key
    echo ""
    echo "   Creating access key..."
    CREDENTIALS=$(aws iam create-access-key --user-name "$IAM_USER" --output json)
    ACCESS_KEY=$(echo "$CREDENTIALS" | grep -o '"AccessKeyId": "[^"]*' | cut -d'"' -f4)
    SECRET_KEY=$(echo "$CREDENTIALS" | grep -o '"SecretAccessKey": "[^"]*' | cut -d'"' -f4)

    echo ""
    echo "========================================"
    echo "SAVE THESE CREDENTIALS (shown only once)"
    echo "========================================"
    echo "AWS_ACCESS_KEY_ID=$ACCESS_KEY"
    echo "AWS_SECRET_ACCESS_KEY=$SECRET_KEY"
    echo "========================================"
else
    echo "   IAM user already exists"
fi

# 5. Output summary
ECR_REGISTRY="${AWS_ACCOUNT_ID}.dkr.ecr.${REGION}.amazonaws.com"

echo ""
echo "========================================"
echo "Setup Complete!"
echo "========================================"
echo ""
echo "GitHub Secrets to add:"
echo "  AWS_ACCESS_KEY_ID     = (from above or existing)"
echo "  AWS_SECRET_ACCESS_KEY = (from above or existing)"
echo "  AWS_REGION            = $REGION"
echo "  AWS_ACCOUNT_ID        = $AWS_ACCOUNT_ID"
echo "  S3_BUCKET             = $BUCKET_NAME"
echo ""
echo "Environment variables for .env file:"
echo "  S3_BUCKET=$BUCKET_NAME"
echo "  S3_ENDPOINT_URL=https://s3.$REGION.amazonaws.com"
echo "  USE_S3=true"
echo "  ECR_REGISTRY=$ECR_REGISTRY"
echo ""
echo "ECR Login command:"
echo "  aws ecr get-login-password --region $REGION | docker login --username AWS --password-stdin $ECR_REGISTRY"
echo ""
echo "Push image command:"
echo "  docker build -t movie-recommender-api -f docker/recommender.Dockerfile ."
echo "  docker tag movie-recommender-api:latest $ECR_REGISTRY/movie-recommender-api:latest"
echo "  docker push $ECR_REGISTRY/movie-recommender-api:latest"
