# 🔧 Исправление KeyError: 118

## ❌ Проблема

При запуске Docker контейнера возникала ошибка:
```
KeyError: 118
```

**Причина:** Gunicorn форкал воркеры до того, как были импортированы классы `TorchLinearSklearnLike` из `train_hier_ext_gpu.py`. Когда joblib пытался десериализовать модели, он не мог найти определение класса.

## ✅ Решение

Добавлен флаг `--preload-app` в команду запуска Gunicorn в `Dockerfile`.

**Что изменилось:**
```dockerfile
# Было:
CMD ["gunicorn", "-w", "2", "-b", "0.0.0.0:8001", "--timeout", "120", "hier_flask_api:app"]

# Стало:
CMD ["gunicorn", "-w", "2", "-b", "0.0.0.0:8001", "--timeout", "120", "--preload-app", "hier_flask_api:app"]
```

**Что делает `--preload-app`:**
- Загружает Flask приложение ДО форка воркеров
- Все импорты и инициализация происходят в главном процессе
- Воркеры наследуют уже загруженное приложение
- Решает проблемы с pickle/joblib при десериализации

## 🚀 Как применить исправление

### Шаг 1: Обновить код из GitHub

```bash
cd /Users/kazybek.kassym/Desktop/DAF/Прокуратура/project00
git pull
```

### Шаг 2: Остановить старый контейнер

```bash
docker compose down
```

### Шаг 3: Пересобрать образ (без кэша!)

```bash
docker compose build --no-cache
```

### Шаг 4: Запустить обновленный контейнер

```bash
docker compose up -d
```

### Шаг 5: Проверить логи

```bash
docker compose logs -f
```

**Ожидаемый результат:**
```
[INFO] Starting gunicorn 21.2.0
[INFO] Listening at: http://0.0.0.0:8001 (1)
[INFO] Using worker: sync
[INFO] Booting worker with pid: 7
[INFO] Booting worker with pid: 8
```

Ошибки `KeyError: 118` больше не должно быть!

### Шаг 6: Протестировать API

```bash
# Health check
curl http://localhost:8001/health

# Тестовый запрос
curl -X POST http://localhost:8001/predict \
  -H "Content-Type: application/json" \
  -d '{
    "text": "Прошу разобраться с начислением штрафа по налогам",
    "topk_cat": 2,
    "topk_sub": 3
  }'
```

## 📊 Дополнительная информация

### Если проблема сохраняется

1. **Уменьшите количество воркеров до 1:**
   
   Отредактируйте `Dockerfile`:
   ```dockerfile
   CMD ["gunicorn", "-w", "1", "-b", "0.0.0.0:8001", "--timeout", "120", "--preload-app", "hier_flask_api:app"]
   ```
   
   Пересоберите: `docker compose build --no-cache && docker compose up -d`

2. **Проверьте, что все файлы на месте:**
   ```bash
   docker compose exec hier-classifier-api ls -la /app/
   ```
   
   Должны быть:
   - `hier_flask_api.py`
   - `train_hier_ext_gpu.py`
   - `artifacts_best_gpu/`

3. **Запустите в режиме отладки:**
   
   Отредактируйте `docker-compose.yml`:
   ```yaml
   environment:
     - FLASK_DEBUG=1
   ```
   
   Перезапустите: `docker compose restart`

### Альтернативное решение (если проблема остается)

Запустите напрямую с Flask (без Gunicorn) для тестирования:

```bash
docker compose down
docker run -it --rm -p 8001:8001 \
  -e FLASK_DEBUG=1 \
  hier-classifier-api \
  python hier_flask_api.py
```

## 🎯 Статус

✅ Исправление применено  
✅ Закоммичено в Git  
✅ Отправлено на GitHub: https://github.com/qazybekq/hierarchical-classifier-api  

Commit: `56d1433` - "Fix joblib unpickle error: add --preload-app flag to Gunicorn"

## 📞 Если нужна помощь

1. Проверьте логи: `docker compose logs -f`
2. Проверьте статус: `docker compose ps`
3. Проверьте Docker: `docker --version`

---

**Дата исправления:** 2025-12-19  
**Проблема:** KeyError: 118 при загрузке joblib моделей  
**Решение:** Добавлен флаг --preload-app в Gunicorn


