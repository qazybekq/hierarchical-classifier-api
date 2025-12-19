# Docker Setup and Testing Instructions

## Prerequisites

1. **Install Docker Desktop**
   - macOS: Download from https://www.docker.com/products/docker-desktop
   - Linux: Follow instructions at https://docs.docker.com/engine/install/
   - Windows: Download from https://www.docker.com/products/docker-desktop

2. **Verify Docker Installation**
   ```bash
   docker --version
   docker compose version
   ```

## Building and Running the Container

### Option 1: Using Docker Compose (Recommended)

1. **Build the image:**
   ```bash
   docker compose build
   ```

2. **Start the service:**
   ```bash
   docker compose up
   ```

3. **Start in detached mode (background):**
   ```bash
   docker compose up -d
   ```

4. **View logs:**
   ```bash
   docker compose logs -f
   ```

5. **Stop the service:**
   ```bash
   docker compose down
   ```

### Option 2: Using Docker Directly

1. **Build the image:**
   ```bash
   docker build -t hier-classifier-api .
   ```

2. **Run the container:**
   ```bash
   docker run -d \
     --name hier-classifier-api \
     -p 8001:8001 \
     hier-classifier-api
   ```

3. **View logs:**
   ```bash
   docker logs -f hier-classifier-api
   ```

4. **Stop and remove:**
   ```bash
   docker stop hier-classifier-api
   docker rm hier-classifier-api
   ```

## Testing the API

### Manual Testing

1. **Health check:**
   ```bash
   curl http://localhost:8001/health
   ```

2. **Test prediction:**
   ```bash
   curl -X POST http://localhost:8001/predict \
     -H "Content-Type: application/json" \
     -d '{
       "text": "Прошу разобраться с начислением штрафа по налогам",
       "topk_cat": 2,
       "topk_sub": 5
     }'
   ```

### Automated Testing

Run the test script (requires `requests` library):

```bash
pip install requests
python test_api.py
```

## Troubleshooting

### Container won't start

Check logs:
```bash
docker compose logs
```

### Port already in use

Change the port in `docker-compose.yml`:
```yaml
ports:
  - "8002:8001"  # Use 8002 instead of 8001
```

### Out of memory

Reduce Gunicorn workers in `Dockerfile`:
```dockerfile
CMD ["gunicorn", "-w", "1", "-b", "0.0.0.0:8001", "--timeout", "120", "hier_flask_api:app"]
```

### Slow first request

The first request downloads the sentence-transformer model (can take 1-2 minutes). Subsequent requests are much faster.

## GPU Support (Optional)

To use GPU acceleration with NVIDIA GPUs:

1. **Install NVIDIA Container Toolkit:**
   Follow instructions at https://docs.nvidia.com/datacenter/cloud-native/container-toolkit/install-guide.html

2. **Update docker-compose.yml:**
   ```yaml
   services:
     hier-classifier-api:
       deploy:
         resources:
           reservations:
             devices:
               - driver: nvidia
                 count: 1
                 capabilities: [gpu]
   ```

3. **Rebuild and run:**
   ```bash
   docker compose up --build
   ```

## Production Deployment

### Increase Workers

For production with more CPU/RAM:
```dockerfile
CMD ["gunicorn", "-w", "4", "-b", "0.0.0.0:8001", "--timeout", "120", "hier_flask_api:app"]
```

### Use Environment Variables

Set environment variables in `docker-compose.yml`:
```yaml
environment:
  - FLASK_DEBUG=0
  - GUNICORN_WORKERS=4
```

### Behind a Reverse Proxy

If using Nginx/Caddy:
```yaml
environment:
  - FORWARDED_ALLOW_IPS=*
```

## Clean Up

Remove all containers and images:
```bash
docker compose down
docker rmi hier-classifier-api
```

Remove unused Docker resources:
```bash
docker system prune -a
```




