# telemetry11

Легкий колектор метрик на Flask з in-memory зберіганням метрик, push та pull інжестом і веб-інтерфейсом для запитів.

## Вимоги

- Python 3.10+

## Швидкий старт (основний застосунок)

1) Підготуйте YAML-конфіг і вкажіть шлях у змінній середовища `TELEMETRY_CONFIG`.
2) Запустіть через Gunicorn:

```bash
TELEMETRY_CONFIG=/path/to/config.yaml \
	gunicorn -c gunicorn.conf.py app:app
```

Примітки:

- Прямий запуск `python app.py` заборонений кодом.
- У процесі зберігаються метрики та працюють фонові треди (скрейпер і федерація), тому `workers=1` у конфігурації Gunicorn.
- Порт для Gunicorn береться з `app-port` у YAML (або 5000, якщо не задано).

## Конфігурація застосунку

Застосунок читає YAML-конфіг за шляхом, вказаним в змінній оточення `TELEMETRY_CONFIG`.

Приклад:

```yaml
push-api: true
internal-metrics: true
metric-retention: 12h
app-port: 5000
federate-refresh-seconds: 60
log-level: INFO
pull:
	scrape-interval-seconds: 15
	endpoints:
		- alias: "node-a"
			endpoint: "http://127.0.0.1:9100/metrics"
		- alias: "node-b"
			endpoint: "http://127.0.0.1:9101/metrics"
			scrape-interval-seconds: 5
```

Параметри:

- `push-api` — вмикає/вимикає інтерфейс надсилання метрик: `POST /api/push` (при `false` повертає 503).
- `internal-metrics` — вмикає/вимикає внутрішні метрики (`internal_*`).
- `metric-retention` — як довго зберігати метрики в сховищі (за замовчуванням `12h`).
	- Формати: `12h`, `30m` або ціле число годин (`12` = `12h`).
- `app-port` — HTTP-порт застосунку (за замовчуванням `5000`).
- `federate-refresh-seconds` — інтервал оновлення снапшота `/federate` (за замовчуванням `60`).
- `log-level` — `DEBUG|INFO|WARNING|ERROR|CRITICAL`.
- `pull.scrape-interval-seconds` — дефолтний інтервал опитування цілей (сек), якщо не задано на рівні цілі (endpoint).
- `pull.endpoints[]` — список цілей опитування:
	- `endpoint` (обовʼязково) — URL метрик.
	- `alias` (опційно) — зручне імʼя для логів і лейблів.
	- `scrape-interval-seconds` (опційно) — перезапис інтервалу лише для цієї цілі.

Сумісний старий формат із однією ціллю також підтримується:

```yaml
pull:
	endpoint: "http://127.0.0.1:9100/metrics"
	alias: "default"
	scrape-interval-seconds: 10
```

## Інжест метрик

### Push

`POST /api/push` приймає JSON:

```json
{"name": "cpu_percent", "value": 10.0, "labels": {"source": "test"}}
```

Додається мітка `method="push"`.

### Pull (скрейпинг)

Коли задані `pull.endpoints`, запускається фоновий скрейпер. Для кожної метрики додаються лейбли:

- `method="scrape"`
- `scrape_alias="<alias>"`

Сторінка `/targets` показує статус скрейпу для кожної цілі.

## Запити та UI

- `/query` і `/dashboard` — сторінка запитів і графіків.
- `/explorer` — каталог метрик.
- `GET /api/metrics?metric=...` — API запиту метрик.

Параметри діапазону (для UI та API):

- `mode=relative|absolute` (за замовчуванням `relative`).
- `minutes` — розмір вікна в хвилинах (дефолт 15).
- `duration` — альтернатива `minutes` у форматі `30m` або `2h` (тільки для `relative`).
- `start` і `end` — ISO 8601 (для `absolute`).

## Механізм федерації

- `GET /federate` — один останній семпл на серію (name + labels) із кешу.
- Кеш оновлюється кожні `federate-refresh-seconds`.

## Перезавантаження конфігурації

`POST /api/reload` перечитує поточний файл `TELEMETRY_CONFIG`. Якщо конфіг некоректний, зберігається попередня робоча конфігурація.

## Внутрішні метрики

Внутрішні метрики з префіксом `internal_` записуються у те саме сховище та видимі у `/explorer` і `/query`.
Вони мають лейбл `method="internal"`.

Основні метрики:

- `internal_total_time_series`
- `internal_total_metrics`
- `internal_query_duration_ms`
- `internal_query_series_count`
- `internal_query_points_count`
- `internal_scrape_targets_total`
- `internal_scrape_targets_success`
- `internal_scrape_targets_fail`
- `internal_scrape_duration_ms`

## OpenAPI та Swagger

- `GET /openapi.json`
- `/swagger`

## Експортер (опційно)

Є окремий системний експортер на базі `psutil`, який віддає метрики у сумісному форматі на `GET /metrics`.

Запуск (окремим процесом через Gunicorn):

```bash
EXPORTER_CONFIG=/path/to/exporter.yaml \
	gunicorn -c exporter/gunicorn.conf.py exporter.exporter:app
```

Мінімальний конфіг для експортера:

```yaml
refresh-seconds: 5
port: 9100
log-level: INFO
labels:
	environment: "dev"
	region: "ukraine"
```

## Контейнеризація

Docker-образ стартує застосунок з Gunicorn. Рекомендований підхід — передати власний конфіг через `TELEMETRY_CONFIG` та змонтувати файл у контейнер.

```bash
docker build -t telemetry11 .
docker run --rm -p 5000:5000 \
	-e TELEMETRY_CONFIG=/config/config.yaml \
	-v /path/to/config.yaml:/config/config.yaml:ro \
	telemetry11
```
