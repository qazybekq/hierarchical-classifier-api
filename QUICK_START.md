# Quick Start Guide

This guide will get you up and running with the Hierarchical Classification API in 5 minutes.

## Prerequisites Checklist

- [ ] Docker and Docker Compose installed
- [ ] At least 4GB RAM available
- [ ] Port 8001 available (or choose another port)

## 3-Step Deployment

### Step 1: Clone the Repository

```bash
git clone https://github.com/YOUR_USERNAME/hierarchical-classifier-api.git
cd hierarchical-classifier-api
```

### Step 2: Start the Service

```bash
docker compose up -d
```

Wait 30-60 seconds for the service to start. The first run may take longer as it downloads the sentence-transformer model.

### Step 3: Test It

```bash
# Health check
curl http://localhost:8001/health

# Make a prediction
curl -X POST http://localhost:8001/predict \
  -H "Content-Type: application/json" \
  -d '{
    "text": "Прошу разобраться с начислением штрафа по налогам",
    "topk_cat": 2,
    "topk_sub": 5
  }'
```

## That's It! 🎉

Your API is now running at `http://localhost:8001`

## What's Next?

### View Logs
```bash
docker compose logs -f
```

### Stop the Service
```bash
docker compose down
```

### Update the Service
```bash
git pull
docker compose up --build -d
```

### Run Automated Tests
```bash
pip install requests
python test_api.py
```

## API Usage Examples

### Python

```python
import requests

response = requests.post(
    "http://localhost:8001/predict",
    json={
        "text": "Отказали в зачислении ребенка в школу",
        "topk_cat": 2,
        "topk_sub": 5
    }
)

result = response.json()
print(f"Top category: {result['predictions'][0]['category']}")
```

### JavaScript

```javascript
fetch('http://localhost:8001/predict', {
  method: 'POST',
  headers: {
    'Content-Type': 'application/json',
  },
  body: JSON.stringify({
    text: 'Отказали в зачислении ребенка в школу',
    topk_cat: 2,
    topk_sub: 5
  })
})
.then(response => response.json())
.then(data => console.log(data));
```

### cURL

```bash
curl -X POST http://localhost:8001/predict \
  -H "Content-Type: application/json" \
  -d @- << EOF
{
  "text": "В больнице не оказали медицинскую помощь",
  "topk_cat": 3,
  "topk_sub": 5
}
EOF
```

## Troubleshooting

### Port Already in Use

Edit `docker-compose.yml` and change the port:
```yaml
ports:
  - "8002:8001"  # Use port 8002 instead
```

### Container Won't Start

Check the logs:
```bash
docker compose logs
```

### Slow Predictions

The first request can be slow (30-60 seconds) as models load into memory. Subsequent requests are much faster (<1 second).

## Configuration

Edit environment variables in `docker-compose.yml`:

```yaml
environment:
  - FLASK_DEBUG=0           # Set to 1 for debug mode
  - DEFAULT_ARTIFACTS_DIR=artifacts_best_gpu
  - FLASK_PORT=8001
```

## Documentation

- Full documentation: `README.md`
- Docker instructions: `DOCKER_INSTRUCTIONS.md`
- GitHub setup: `GITHUB_SETUP.md`
- API endpoint details: See `hier_flask_api.py` docstring

## Support

- Issues: Create an issue on GitHub
- Questions: Open a discussion on GitHub

---

**Pro Tip**: Bookmark `http://localhost:8001/health` to quickly check if the service is running!



