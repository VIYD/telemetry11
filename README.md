# Telemetry11 — Запуск та встановлення

## 1. Створення віртуального середовища

### Linux
```
python3 -m venv .venv
source .venv/bin/activate
```

### Windows
```
C:\Python\python.exe -m venv .venv
.\.venv\Scripts\Activate.ps1
```

(шлях до Python.exe та його виклик може відрізнятись)

---

## 2. Встановлення залежностей
```
pip install -r requirements.txt
```

---

## 3. Встановлення Waitress (лише для Windows)
```powershell
pip install waitress
```

---

## 4. Запуск основного застосунку

### Linux (Gunicorn)
```
TELEMETRY_CONFIG=/path/to/telemetry.yaml \
gunicorn -c gunicorn.conf.py app:app
```

### Windows (через Waitress)
```
$env:TELEMETRY_CONFIG="D:\dev\telemetry11\examples\configs\telemetry.yaml" \
C:\Python\python.exe -m waitress --listen=0.0.0.0:5000 app:app
```

(порт задається в аргументі listen)

---

## 5. Запуск експортера

### Linux
```
EXPORTER_CONFIG=/path/to/exporter.yaml \
gunicorn -c exporter/gunicorn.conf.py exporter.exporter:app
```

### Windows
```
$env:EXPORTER_CONFIG="D:\dev\telemetry11\examples\configs\exporter.yaml" \
C:\Python\python.exe -m waitress --listen=0.0.0.0:9100 exporter.exporter:app
```

---

## 6. Docker (опційно)

```
docker build -t telemetry11 .

docker run --rm -p 5000:5000 \
-e TELEMETRY_CONFIG=/config/telemetry.yaml \
-v /examples/configs/telemetry.yaml:/config/telemetry.yaml:ro \
telemetry11
```