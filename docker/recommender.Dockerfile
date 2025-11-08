# docker/recommender.Dockerfile
FROM python:3.11-slim

# Set working directory
WORKDIR /app

# Copy requirements first for build caching
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy the entire repo (not just subfolders)
COPY . .

# Expose port and set defaults
ENV PORT=8080
EXPOSE 8080

# Start FastAPI app
CMD ["uvicorn", "service.app:app", "--host", "0.0.0.0", "--port", "8080"]
