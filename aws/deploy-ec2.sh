#!/bin/bash
# Quick deployment script for AWS EC2
# This script launches an EC2 instance and deploys the movie recommender system

set -e

echo "🚀 Deploying Movie Recommender to AWS EC2..."

# Configuration
REGION=${AWS_REGION:-us-east-1}
INSTANCE_TYPE=${INSTANCE_TYPE:-t3.medium}
KEY_NAME=${AWS_KEY_NAME:-your-key-pair}
SECURITY_GROUP=${SECURITY_GROUP:-sg-xxxxxxxx}
SUBNET=${SUBNET:-subnet-xxxxxxxx}

# AMI for Ubuntu 22.04 in us-east-1 (update for your region)
AMI_ID="ami-0c55b159cbfafe1f0"

echo "📋 Configuration:"
echo "  Region: $REGION"
echo "  Instance Type: $INSTANCE_TYPE"
echo "  Key Name: $KEY_NAME"
echo ""

# Step 1: Launch EC2 instance
echo "1️⃣  Launching EC2 instance..."
INSTANCE_ID=$(aws ec2 run-instances \
  --region $REGION \
  --image-id $AMI_ID \
  --instance-type $INSTANCE_TYPE \
  --key-name $KEY_NAME \
  --security-group-ids $SECURITY_GROUP \
  --subnet-id $SUBNET \
  --tag-specifications 'ResourceType=instance,Tags=[{Key=Name,Value=movie-recommender}]' \
  --query 'Instances[0].InstanceId' \
  --output text)

echo "*  Instance launched: $INSTANCE_ID"

# Step 2: Wait for instance to be running
echo "2️⃣  Waiting for instance to be running..."
aws ec2 wait instance-running --region $REGION --instance-ids $INSTANCE_ID
echo "*  Instance is running"

# Step 3: Get public IP
PUBLIC_IP=$(aws ec2 describe-instances \
  --region $REGION \
  --instance-ids $INSTANCE_ID \
  --query 'Reservations[0].Instances[0].PublicIpAddress' \
  --output text)

echo "*  Public IP: $PUBLIC_IP"

# Step 4: Wait for SSH to be ready
echo "3️⃣  Waiting for SSH to be ready (this may take a minute)..."
sleep 30

# Step 5: Setup instance
echo "4️⃣  Setting up instance..."
ssh -i ~/.ssh/${KEY_NAME}.pem -o StrictHostKeyChecking=no ubuntu@$PUBLIC_IP << 'EOF'
  # Update system
  sudo apt-get update
  sudo apt-get install -y docker.io docker-compose git

  # Start Docker
  sudo systemctl start docker
  sudo systemctl enable docker
  sudo usermod -aG docker ubuntu

  echo "*  Docker installed"
EOF

# Step 6: Deploy application
echo "5️⃣  Deploying application..."
REPO_URL=${REPO_URL:-https://github.com/your-username/your-repo.git}

ssh -i ~/.ssh/${KEY_NAME}.pem ubuntu@$PUBLIC_IP << EOF
  # Clone repository
  git clone $REPO_URL movie-recommender
  cd movie-recommender

  # Start services
  sudo docker-compose up -d

  echo "*  Application deployed"
EOF

# Step 7: Allocate and associate Elastic IP (optional)
echo "6️⃣  Allocating Elastic IP..."
ALLOCATION_ID=$(aws ec2 allocate-address --region $REGION --domain vpc --query 'AllocationId' --output text)
ELASTIC_IP=$(aws ec2 describe-addresses --region $REGION --allocation-ids $ALLOCATION_ID --query 'Addresses[0].PublicIp' --output text)

aws ec2 associate-address --region $REGION --instance-id $INSTANCE_ID --allocation-id $ALLOCATION_ID
echo "*  Elastic IP allocated: $ELASTIC_IP"

# Summary
echo ""
echo "╔══════════════════════════════════════════════════════════════╗"
echo "║            DEPLOYMENT COMPLETE                                ║"
echo "╚══════════════════════════════════════════════════════════════╝"
echo ""
echo "Instance ID:    $INSTANCE_ID"
echo "Elastic IP:     $ELASTIC_IP"
echo ""
echo "API Endpoints:"
echo "  Health:       http://$ELASTIC_IP:8080/healthz"
echo "  Recommend:    http://$ELASTIC_IP:8080/recommend/{user_id}?k=10"
echo "  Metrics:      http://$ELASTIC_IP:8080/metrics"
echo "  Prometheus:   http://$ELASTIC_IP:9090"
echo "  Grafana:      http://$ELASTIC_IP:3000"
echo ""
echo "SSH Access:"
echo "  ssh -i ~/.ssh/${KEY_NAME}.pem ubuntu@$ELASTIC_IP"
echo ""
echo "To stop services:"
echo "  ssh -i ~/.ssh/${KEY_NAME}.pem ubuntu@$ELASTIC_IP 'cd movie-recommender && sudo docker-compose down'"
echo ""
echo "To terminate instance:"
echo "  aws ec2 terminate-instances --region $REGION --instance-ids $INSTANCE_ID"
echo "  aws ec2 release-address --region $REGION --allocation-id $ALLOCATION_ID"
echo ""
