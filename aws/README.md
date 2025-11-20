# AWS Deployment Quick Start

This directory contains AWS deployment configurations for the Movie Recommender System.

---

## Quick Deployment (EC2 + Docker Compose)

**Simplest option - Same setup as local, but on AWS**

### Prerequisites

1. AWS account with appropriate permissions
2. AWS CLI configured (`aws configure`)
3. EC2 key pair created
4. VPC with public subnet
5. Security group allowing ports: 22, 8080, 9090, 3000

### Automated Deployment

```bash
# Set your configuration
export AWS_REGION=us-east-1
export AWS_KEY_NAME=your-key-pair
export SECURITY_GROUP=sg-xxxxxxxx
export SUBNET=subnet-xxxxxxxx
export REPO_URL=https://github.com/your-username/your-repo.git

# Run deployment script
chmod +x aws/deploy-ec2.sh
./aws/deploy-ec2.sh
```

The script will:
1. Launch t3.medium EC2 instance
2. Install Docker and Docker Compose
3. Clone your repository
4. Start all services via docker-compose
5. Allocate Elastic IP
6. Output all URLs

### Manual Deployment Steps

If you prefer manual control:

```bash
# 1. Launch instance
aws ec2 run-instances \
  --image-id ami-0c55b159cbfafe1f0 \
  --instance-type t3.medium \
  --key-name your-key-pair \
  --security-group-ids sg-xxxxxxxx \
  --subnet-id subnet-xxxxxxxx

# 2. SSH to instance
ssh -i your-key.pem ubuntu@<instance-ip>

# 3. Install Docker
sudo apt-get update
sudo apt-get install -y docker.io docker-compose git

# 4. Clone and start
git clone <your-repo-url>
cd <repo-directory>
sudo docker-compose up -d

# 5. Verify
curl http://localhost:8080/healthz
```

---

## Security Group Configuration

Create a security group with these inbound rules:

| Type | Protocol | Port | Source | Description |
|------|----------|------|--------|-------------|
| SSH | TCP | 22 | Your IP | SSH access |
| Custom TCP | TCP | 8080 | 0.0.0.0/0 | API |
| Custom TCP | TCP | 9090 | 0.0.0.0/0 | Prometheus |
| Custom TCP | TCP | 3000 | 0.0.0.0/0 | Grafana |

**Production**: Restrict Prometheus (9090) and Grafana (3000) to your IP only.

---

## Verifying Deployment

```bash
# Get your instance's public IP
PUBLIC_IP=$(aws ec2 describe-instances \
  --filters "Name=tag:Name,Values=movie-recommender" \
  --query 'Reservations[0].Instances[0].PublicIpAddress' \
  --output text)

# Test endpoints
curl http://$PUBLIC_IP:8080/healthz
curl http://$PUBLIC_IP:8080/recommend/123?k=10
curl http://$PUBLIC_IP:8080/metrics

# Access dashboards
open http://$PUBLIC_IP:9090  # Prometheus
open http://$PUBLIC_IP:3000  # Grafana
```

---

## Collecting Evidence from AWS

Update the scripts to point to your AWS instance:

```bash
# Calculate availability from AWS
python scripts/calculate_availability.py \
  --prometheus-url http://$PUBLIC_IP:9090 \
  --hours 72

# Verify model updates
python scripts/verify_model_updates.py \
  --prometheus-url http://$PUBLIC_IP:9090

# Collect evidence
python scripts/collect_evidence.py \
  --api-url http://$PUBLIC_IP:8080 \
  --prometheus-url http://$PUBLIC_IP:9090 \
  --output evidence/
```

---

## Monitoring AWS Deployment

### SSH to Instance

```bash
ssh -i your-key.pem ubuntu@$PUBLIC_IP

# View logs
sudo docker-compose logs -f api

# Check services
sudo docker-compose ps

# Restart services
sudo docker-compose restart api
```

### CloudWatch Integration (Optional)

For better AWS integration, add CloudWatch logging:

```python
# In service/app.py
import watchtower
import logging

logger = logging.getLogger()
logger.addHandler(watchtower.CloudWatchLogHandler(
    log_group='/aws/movie-recommender',
    stream_name='api'
))
```

Install dependency:
```bash
pip install watchtower
```

---

## Cost Management

### Estimated Monthly Costs

| Resource | Cost |
|----------|------|
| t3.medium (730 hrs) | ~$30 |
| EBS 50GB | ~$4 |
| Data transfer (100GB) | ~$9 |
| Elastic IP | Free (if attached) |
| **Total** | **~$43/month** |

### Cost Optimization

1. **Use Free Tier** (first 12 months):
   - 750 hours/month t2.micro or t3.micro
   - Change instance type to t3.micro: saves ~$20/month

2. **Stop when not needed**:
   ```bash
   aws ec2 stop-instances --instance-ids i-xxxxxxxx
   ```

3. **Set up billing alert**:
   ```bash
   aws cloudwatch put-metric-alarm \
     --alarm-name high-billing \
     --alarm-description "Alert when bill exceeds $50" \
     --metric-name EstimatedCharges \
     --namespace AWS/Billing \
     --statistic Maximum \
     --period 21600 \
     --threshold 50 \
     --comparison-operator GreaterThanThreshold
   ```

---

## Troubleshooting

### Cannot connect to instance

```bash
# Check instance is running
aws ec2 describe-instances --instance-ids i-xxxxxxxx

# Check security group allows your IP
aws ec2 describe-security-groups --group-ids sg-xxxxxxxx

# Try from different network (VPN might block)
```

### Services not starting

```bash
# SSH to instance
ssh -i your-key.pem ubuntu@$PUBLIC_IP

# Check Docker
sudo systemctl status docker

# View logs
sudo docker-compose logs

# Restart services
sudo docker-compose down
sudo docker-compose up -d
```

### Out of disk space

```bash
# Check disk usage
df -h

# Clean Docker images
sudo docker system prune -a

# Increase EBS volume size if needed
```

---

## Cleanup (After Submission)

```bash
# Get instance and allocation IDs
INSTANCE_ID=$(aws ec2 describe-instances \
  --filters "Name=tag:Name,Values=movie-recommender" \
  --query 'Reservations[0].Instances[0].InstanceId' \
  --output text)

ALLOCATION_ID=$(aws ec2 describe-addresses \
  --filters "Name=instance-id,Values=$INSTANCE_ID" \
  --query 'Addresses[0].AllocationId' \
  --output text)

# Terminate instance
aws ec2 terminate-instances --instance-ids $INSTANCE_ID

# Release Elastic IP
aws ec2 release-address --allocation-id $ALLOCATION_ID

# Verify cleanup
aws ec2 describe-instances --instance-ids $INSTANCE_ID
```

---

## Alternative: Using Existing Compute

If you already have:
- **Personal server**: Deploy there instead
- **University resources**: Check if available
- **Free tier cloud**: Google Cloud, Azure also work

The Docker Compose setup works anywhere!

---

## For the Report

In your submission, include:

1. **Public URL**: `http://<elastic-ip>:8080`
2. **Availability calculation** from the AWS deployment
3. **Screenshot** showing AWS EC2 console with running instance
4. **Prometheus URL**: `http://<elastic-ip>:9090`
5. **Note**: "Deployed on AWS EC2 t3.medium instance in us-east-1"

This proves the system runs in production, not just locally!

---

## Next Steps

1. Deploy to AWS using `deploy-ec2.sh`
2. Let it run for 72+ hours
3. Verify with `calculate_availability.py` pointing to AWS
4. Collect evidence from AWS deployment
5. Include AWS URLs in final report
6. Clean up after grading to avoid charges
