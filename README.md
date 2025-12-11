# Hierarchical Text Classification API

A production-ready Flask API for hierarchical text classification using sentence transformers and PyTorch linear classifiers. This microservice classifies text requests into categories and subcategories for government complaint routing.

## 🚀 Features

- **Hierarchical Classification**: Two-stage classification (router → category heads)
- **GPU Support**: Automatic device detection (CUDA/MPS/CPU)
- **Production Ready**: Dockerized with health checks and Gunicorn
- **Multilingual**: Uses `paraphrase-multilingual-mpnet-base-v2` model
- **REST API**: Simple JSON-based HTTP interface
- **Caching**: Efficient model and artifacts caching

## 📋 Prerequisites

- Docker and Docker Compose
- At least 4GB RAM available for Docker
- (Optional) NVIDIA GPU with Docker GPU support for faster inference

## 🐳 Quick Start with Docker

### 1. Clone the repository

```bash
git clone <your-repo-url>
cd project00
```

### 2. Build and run with Docker Compose

```bash
docker-compose up --build
```

The API will be available at `http://localhost:8001`

### 3. Test the API

**Health check:**
```bash
curl http://localhost:8001/health
```

**Prediction:**
```bash
curl -X POST http://localhost:8001/predict \
  -H "Content-Type: application/json" \
  -d '{
    "text": "Прошу разобраться с начислением штрафа по налогам",
    "topk_cat": 2,
    "topk_sub": 5
  }'
```

## 🔧 Manual Installation (Without Docker)

### 1. Install dependencies

```bash
pip install -r requirements.txt
```

### 2. Run the application

```bash
export ARTIFACTS_ROOT=$(pwd)
export DEFAULT_ARTIFACTS_DIR=artifacts_best_gpu
python hier_flask_api.py
```

Or with Gunicorn:
```bash
gunicorn -w 2 -b 0.0.0.0:8001 hier_flask_api:app
```

## 📖 API Documentation

### Endpoints

#### `GET /health`
Health check endpoint.

**Response:**
```json
{
  "status": "ok"
}
```

#### `POST /predict`
Classify input text.

**Request Body:**
```json
{
  "text": "Your text here",
  "art_dir": "artifacts_best_gpu",  // optional
  "device": "auto",                  // optional: auto|cpu|cuda|mps
  "topk_cat": 2,                     // optional: number of top categories
  "topk_sub": 5                      // optional: number of top subissues
}
```

**Response:**
```json
{
  "art_dir": "artifacts_best_gpu",
  "device_effective": "cuda",
  "st_model_name": "sentence-transformers/paraphrase-multilingual-mpnet-base-v2",
  "router_topk": 2,
  "sub_topk": 5,
  "predictions": [
    {
      "category": "ТАМОЖЕННОЕ И НАЛОГОВОЕ АДМИНИСТРИРОВАНИЕ",
      "proba": 0.87,
      "subissues": [
        {
          "label": "Налогообложение__SEP__Штрафы и пени",
          "issue": "Налогообложение",
          "subissue_unique": "Штрафы и пени",
          "proba": 0.62
        }
      ]
    }
  ]
}
```

## 🏗️ Project Structure

```
project00/
├── hier_flask_api.py           # Flask API application
├── train_hier_ext_gpu.py       # Training script (required for unpickling)
├── requirements.txt            # Python dependencies
├── Dockerfile                  # Docker configuration
├── docker-compose.yml          # Docker Compose configuration
├── .dockerignore              # Docker ignore patterns
├── .gitignore                 # Git ignore patterns
├── README.md                  # This file
└── artifacts_best_gpu/        # Pre-trained model artifacts
    ├── cat_router.joblib
    ├── cat_label_encoder.joblib
    ├── cat_stats.json
    ├── mapping.json
    ├── meta.json
    ├── st_model/              # Sentence transformer model
    └── models/                # Category-specific classifiers
        ├── CATEGORY_1__hash/
        │   ├── clf.joblib
        │   ├── label_encoder.joblib
        │   └── stats.json
        └── ...
```

## 🔧 Configuration

Environment variables:

| Variable | Default | Description |
|----------|---------|-------------|
| `ARTIFACTS_ROOT` | `.` | Root directory for artifacts |
| `DEFAULT_ARTIFACTS_DIR` | `artifacts_best_gpu` | Default artifacts folder name |
| `ST_MODEL_NAME` | `sentence-transformers/paraphrase-multilingual-mpnet-base-v2` | Sentence transformer model |
| `FLASK_HOST` | `0.0.0.0` | Flask host |
| `FLASK_PORT` | `8001` | Flask port |
| `FLASK_DEBUG` | `0` | Debug mode (0 or 1) |

## 🐛 Troubleshooting

### Container fails to start

Check logs:
```bash
docker-compose logs -f
```

### Out of memory

Reduce the number of Gunicorn workers in `Dockerfile`:
```dockerfile
CMD ["gunicorn", "-w", "1", "-b", "0.0.0.0:8001", "--timeout", "120", "hier_flask_api:app"]
```

### Slow predictions

- Use GPU if available
- Reduce `topk_cat` and `topk_sub` in requests
- Increase Gunicorn workers if you have enough RAM

## 📊 Model Information

- **Router**: 45-class category classifier
- **Category Heads**: Per-category subcategory classifiers
- **Embedding Model**: `paraphrase-multilingual-mpnet-base-v2` (768-dim)
- **Training**: Linear heads trained with AdamW + Cosine Annealing

## 🤝 Contributing

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Submit a pull request

## 📝 License

[Add your license here]

## 👥 Authors

[Add your name/team here]

## 🙏 Acknowledgments

- Sentence-Transformers library
- PyTorch and scikit-learn communities

