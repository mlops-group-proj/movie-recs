# AWS Deployment Guide

This guide covers deploying the Movie Recommender System to AWS for production availability verification.

---

## Deployment Options

### Option 1: AWS ECS (Recommended)
- **Pros**: Native Docker support, auto-scaling, managed service
- **Cons**: More AWS-specific configuration
- **Best for**: Production workloads

### Option 2: AWS EC2 + Docker Compose
- **Pros**: Simple, same as local setup
- **Cons**: Manual management, no auto-scaling
- **Best for**: Quick deployment, development

### Option 3: AWS App Runner
- **Pros**: Simplest deployment, auto-scaling
- **Cons**: Limited customization
- **Best for**: Stateless services

---

## Option 1: AWS ECS Deployment (Recommended)

### Prerequisites

```bash
# Install AWS CLI
brew install awscli  # macOS
pip install awscli   # Any platform

# Configure AWS credentials
aws configure
```

### Step 1: Push Images to ECR

```bash
# Create ECR repositories
aws ecr create-repository --repository-name movie-recommender/api
aws ecr create-repository --repository-name movie-recommender/ingestor

# Get login credentials
aws ecr get-login-password --region us-east-1 | docker login --username AWS --password-stdin <account-id>.dkr.ecr.us-east-1.amazonaws.com

# Tag and push images
docker tag movie-recommender-api:latest <account-id>.dkr.ecr.us-east-1.amazonaws.com/movie-recommender/api:latest
docker push <account-id>.dkr.ecr.us-east-1.amazonaws.com/movie-recommender/api:latest

docker tag movie-recommender-ingestor:latest <account-id>.dkr.ecr.us-east-1.amazonaws.com/movie-recommender/ingestor:latest
docker push <account-id>.dkr.ecr.us-east-1.amazonaws.com/movie-recommender/ingestor:latest
```

### Step 2: Create ECS Task Definitions

See `aws/ecs-task-definition.json` (created below)

### Step 3: Deploy with CloudFormation

```bash
aws cloudformation create-stack \
  --stack-name movie-recommender \
  --template-body file://aws/cloudformation-template.yaml \
  --capabilities CAPABILITY_IAM
```

### Step 4: Verify Deployment

```bash
# Get load balancer DNS
aws elbv2 describe-load-balancers --names movie-recommender-alb --query 'LoadBalancers[0].DNSName'

# Test API
curl http://<load-balancer-dns>/healthz
```

---

## Option 2: EC2 + Docker Compose (Simple)

### Step 1: Launch EC2 Instance

```bash
# Launch Ubuntu instance (t3.medium recommended)
aws ec2 run-instances \
  --image-id ami-0c55b159cbfafe1f0 \
  --instance-type t3.medium \
  --key-name your-key-pair \
  --security-group-ids sg-xxxxxxxx \
  --subnet-id subnet-xxxxxxxx \
  --tag-specifications 'ResourceType=instance,Tags=[{Key=Name,Value=movie-recommender}]'
```

### Step 2: Connect and Setup

```bash
# SSH to instance
ssh -i your-key.pem ubuntu@<instance-ip>

# Install Docker and Docker Compose
sudo apt-get update
sudo apt-get install -y docker.io docker-compose git

# Clone repository
git clone <your-repo-url>
cd <repo-directory>

# Start services
sudo docker-compose up -d
```

### Step 3: Configure Security Group

Allow inbound traffic:
- Port 8080 (API)
- Port 9090 (Prometheus)
- Port 3000 (Grafana)
- Port 22 (SSH)

### Step 4: Setup Elastic IP (Optional but Recommended)

```bash
# Allocate Elastic IP
aws ec2 allocate-address --domain vpc

# Associate with instance
aws ec2 associate-address --instance-id <instance-id> --allocation-id <eip-allocation-id>
```

---

## Option 3: AWS App Runner

### Step 1: Create apprunner.yaml

```yaml
version: 1.0
runtime: python3.11
build:
  commands:
    build:
      - pip install -r reqs-recommender.txt
run:
  command: uvicorn service.app:app --host 0.0.0.0 --port 8080
  network:
    port: 8080
```

### Step 2: Deploy

```bash
aws apprunner create-service \
  --service-name movie-recommender \
  --source-configuration file://apprunner-source.json
```

---

## Monitoring Setup on AWS

### CloudWatch Integration

Add to `service/app.py`:

```python
import boto3
from datetime import datetime

cloudwatch = boto3.client('cloudwatch', region_name='us-east-1')

def send_metric(metric_name, value, unit='None'):
    cloudwatch.put_metric_data(
        Namespace='MovieRecommender',
        MetricData=[{
            'MetricName': metric_name,
            'Value': value,
            'Unit': unit,
            'Timestamp': datetime.utcnow()
        }]
    )

# In recommend endpoint
send_metric('RequestLatency', latency * 1000, 'Milliseconds')
send_metric('SuccessfulRequests', 1, 'Count')
```

### CloudWatch Logs

```python
import watchtower
import logging

# Setup CloudWatch handler
logger = logging.getLogger()
logger.addHandler(watchtower.CloudWatchLogHandler(
    log_group='/aws/ecs/movie-recommender',
    stream_name='api'
))
```

---

## Automated Retraining on AWS

### Option A: EventBridge + Lambda + ECS Task

1. **Lambda Function** (triggers training):
```python
import boto3

def lambda_handler(event, context):
    ecs = boto3.client('ecs')

    response = ecs.run_task(
        cluster='movie-recommender-cluster',
        taskDefinition='training-task',
        launchType='FARGATE'
    )

    return {'statusCode': 200, 'body': 'Training started'}
```

2. **EventBridge Rule** (schedule):
```bash
aws events put-rule \
  --name daily-retraining \
  --schedule-expression "cron(0 2 * * ? *)"
```

### Option B: EC2 Cron (Simpler)

If using EC2 deployment:

```bash
# On EC2 instance
crontab -e

# Add daily training at 2 AM
0 2 * * * cd /path/to/repo && docker-compose run training
```

---

## Cost Estimation

### ECS Deployment (Monthly)

| Resource | Specs | Cost |
|----------|-------|------|
| ECS Fargate (API) | 1 vCPU, 2GB RAM | ~$30 |
| ECS Fargate (Prometheus) | 0.5 vCPU, 1GB RAM | ~$15 |
| ALB | Application Load Balancer | ~$20 |
| ECR | Image storage (5GB) | ~$0.50 |
| Data Transfer | ~100GB/month | ~$9 |
| **Total** | | **~$75/month** |

### EC2 Deployment (Monthly)

| Resource | Specs | Cost |
|----------|-------|------|
| EC2 t3.medium | 2 vCPU, 4GB RAM | ~$30 |
| EBS Storage | 50GB gp3 | ~$4 |
| Elastic IP | 1 static IP | Free (if attached) |
| Data Transfer | ~100GB/month | ~$9 |
| **Total** | | **~$43/month** |

### Free Tier Eligible

- First 12 months: 750 hours/month EC2 t2.micro (covers 24/7)
- 50GB S3 storage
- 5GB CloudWatch Logs

---

## Production Checklist

Before deploying to AWS:

- [ ] Environment variables configured
- [ ] Secrets stored in AWS Secrets Manager
- [ ] Security groups properly configured
- [ ] Backup strategy for model registry
- [ ] Monitoring and alerting set up
- [ ] Auto-scaling policies defined
- [ ] Cost alerts configured
- [ ] SSL/TLS certificates installed
- [ ] Domain name configured (optional)
- [ ] CI/CD pipeline set up (optional)

---

## Security Best Practices

### 1. Use AWS Secrets Manager

```python
import boto3
import json

def get_secret(secret_name):
    client = boto3.client('secretsmanager', region_name='us-east-1')
    response = client.get_secret_value(SecretId=secret_name)
    return json.loads(response['SecretString'])

# Usage
db_creds = get_secret('movie-recommender/db')
```

### 2. Enable VPC Flow Logs

```bash
aws ec2 create-flow-logs \
  --resource-type VPC \
  --resource-ids vpc-xxxxxxxx \
  --traffic-type ALL \
  --log-destination-type cloud-watch-logs \
  --log-group-name /aws/vpc/flowlogs
```

### 3. Use IAM Roles (Not Access Keys)

Attach IAM role to ECS task or EC2 instance instead of embedding credentials.

---

## Troubleshooting

### Cannot connect to API

```bash
# Check security group allows port 8080
aws ec2 describe-security-groups --group-ids sg-xxxxxxxx

# Check ECS tasks are running
aws ecs list-tasks --cluster movie-recommender-cluster

# Check logs
aws logs tail /aws/ecs/movie-recommender-api --follow
```

### High costs

```bash
# Check what's running
aws ecs list-tasks --cluster movie-recommender-cluster
aws ec2 describe-instances --filters "Name=instance-state-name,Values=running"

# Stop unnecessary resources
aws ecs update-service --cluster movie-recommender-cluster --service api --desired-count 0
```

---

## Cleanup (After Submission)

```bash
# Delete CloudFormation stack
aws cloudformation delete-stack --stack-name movie-recommender

# Delete ECR repositories
aws ecr delete-repository --repository-name movie-recommender/api --force
aws ecr delete-repository --repository-name movie-recommender/ingestor --force

# Terminate EC2 instances
aws ec2 terminate-instances --instance-ids i-xxxxxxxx

# Release Elastic IP
aws ec2 release-address --allocation-id eipalloc-xxxxxxxx
```

---

## Next Steps

See deployment configuration files:
- `aws/cloudformation-template.yaml`
- `aws/ecs-task-definition.json`
- `aws/deploy.sh` (automated deployment script)
