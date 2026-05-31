# Telemetry11

| Поле | Значення |
| --- | --- |
| **ПІБ** | Поляков Олександр Юрійович |
| **Група** | ФЕІ-42с |
| **Спеціальність** | 122 — Комп'ютерні науки |
| **Науковий керівник** | ас. Гусак Олег |
| **Рецензент** | проф. Карбовник Іван |

Telemetry11 — моніторинговий застосунок для приймання, зберігання та перегляду метрик з вбудованим експортером. Проєкт містить веб-інтерфейс, JSON API та конфігурацію через YAML.

## Функціонал

- Прийом метрик через `POST /api/push` та збереження в локальному сховищі.
- Запити часових рядів через `GET /api/metrics` та перегляд через сторінку запитів.
- Веб-інтерфейс для огляду стану, метрик, цілей збору та каталогу метрик.
- Експортер системних метрик з ендпоїнтом `GET /metrics` та перевіркою `GET /health`.
- Перезавантаження конфігурації без зупинки сервера через `POST /api/reload`.
- OpenAPI JSON та Swagger UI для API.

## Стек технологій

- Python 3.x.
- Flask (WSGI веб-застосунок).
- Gunicorn для Linux/macOS, Waitress для Windows.
- PyYAML для читання конфігурації.
- psutil для збору системних метрик.

## Опис файлів і структури

| Шлях | Призначення |
| --- | --- |
| [app.py](app.py) | Ініціалізація та запуск основного застосунку. |
| [routes.py](routes.py) | Маршрути веб-інтерфейсу та API. |
| [api_docs.py](api_docs.py) | Формування OpenAPI специфікації. |
| [kernel](kernel) | Ініціалізація налаштувань, застосування дефолтів, перезавантаження конфігурації та запуск фонових циклів (федерування, скрапінг, внутрішні метрики). |
| [metrics](metrics) | Інжест і валідація метрик, зберігання в сховищі, запити часових рядів, каталог/огляд метрик і політики ретенції. |
| [exporter](exporter) | Окремий застосунок-експортер системних метрик. |
| [templates](templates) | HTML-шаблони сторінок інтерфейсу. |
| [examples/configs](examples/configs) | Приклади YAML-конфігурацій. |
| [examples/dockerfiles](examples/dockerfiles) | Docker і docker-compose приклади. |
| [requirements.txt](requirements.txt) | Python-залежності. |
| [gunicorn.conf.py](gunicorn.conf.py) | Конфігурація Gunicorn для основного застосунку. |
| [exporter/gunicorn.conf.py](exporter/gunicorn.conf.py) | Конфігурація Gunicorn для експортера. |
| [Dockerfile](Dockerfile) | Образ для запуску основного застосунку. |
| [Makefile](Makefile) | Команди для локальних задач. |
| [scripts/push.sh](scripts/push.sh) | Приклад скрипта для push-запиту метрик. |

## Скріншоти

![Запити метрик](pictures/query.png)
![Огляд метрик](pictures/explorer.png)
![Огляд цілей опитування](pictures/targets.png)

## Запуск

### Передумови

- Встановлений Python 3.x.
- Налаштований конфігураційний файл YAML для основного застосунку та експортера.

Приклади конфігурацій: [examples/configs/telemetry.yaml](examples/configs/telemetry.yaml), [examples/configs/telemetry_federate.yaml](examples/configs/telemetry_federate.yaml), [examples/configs/exporter.yaml](examples/configs/exporter.yaml).

### Створення віртуального середовища

Linux/macOS:

```
python3 -m venv .venv
source .venv/bin/activate
```

Windows:

```
C:\Python\python.exe -m venv .venv
\.venv\Scripts\Activate.ps1
```

### Встановлення залежностей

```
pip install -r requirements.txt
```

### Встановлення Waitress (лише для Windows)

```powershell
pip install waitress
```

### Запуск основного застосунку

Linux/macOS (Gunicorn):

```
TELEMETRY_CONFIG=/path/to/telemetry.yaml \
gunicorn -c gunicorn.conf.py app:app
```

Windows (Waitress):

```powershell
$env:TELEMETRY_CONFIG="D:\dev\telemetry11\examples\configs\telemetry.yaml"
C:\Python\python.exe -m waitress --listen=0.0.0.0:5000 app:app
```

### Запуск експортера

Linux/macOS:

```
EXPORTER_CONFIG=/path/to/exporter.yaml \
gunicorn -c exporter/gunicorn.conf.py exporter.exporter:app
```

Windows:

```powershell
$env:EXPORTER_CONFIG="D:\dev\telemetry11\examples\configs\exporter.yaml"
C:\Python\python.exe -m waitress --listen=0.0.0.0:9100 exporter.exporter:app
```

### Docker (опційно)

```
docker build -t telemetry11 .

docker run --rm -p 5000:5000 \
-e TELEMETRY_CONFIG=/config/telemetry.yaml \
-v /examples/configs/telemetry.yaml:/config/telemetry.yaml:ro \
telemetry11
```

## Інструкція з користування

- Відкрийте головну сторінку за адресою `http://localhost:5000/` та перевірте доступність інтерфейсу.
- Для перегляду метрик використовуйте сторінки `GET /query`, `GET /explorer`, `GET /status`.
- Для інтеграції з іншими системами використовуйте JSON API `GET /api/metrics`.
- Для відправки метрик по push виконайте запит `POST /api/push`.
- Для перевірки експортера відкрийте `GET /metrics` або `GET /health` на порту експортера.
- Для оновлення налаштувань без перезапуску застосунку використовуйте `POST /api/reload`.
- Документація API доступна на `GET /openapi.json` і `GET /swagger`.

## Типові проблеми

- `ModuleNotFoundError` або `ImportError` — перевірте, що виконали `pip install -r requirements.txt` у активному віртуальному середовищі.
- Повідомлення про заборону прямого запуску — застосунок потрібно запускати через Gunicorn або Waitress.
- `TELEMETRY_CONFIG` або `EXPORTER_CONFIG` не вказані — встановіть змінні оточення перед запуском.
- Конфігурація YAML не читається — переконайтесь, що файл існує і має валідний синтаксис.
- Помилка "Address already in use" — змініть порт у команді запуску або звільніть порт.