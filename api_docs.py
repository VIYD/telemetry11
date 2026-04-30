from flask import jsonify, render_template


def _openapi_spec():
    return {
        "openapi": "3.0.3",
        "info": {
            "title": "Telemetry11 API",
            "version": "1.0.0",
            "description": "HTTP API for ingesting, querying, and federating telemetry metrics.",
        },
        "paths": {
            "/api/metrics": {
                "get": {
                    "summary": "Query metric series",
                    "parameters": [
                        {
                            "name": "metric",
                            "in": "query",
                            "required": True,
                            "schema": {"type": "string"},
                            "description": "Metric selector, e.g. cpu_percent or cpu_percent{host=\"node-1\"}",
                        },
                        {
                            "name": "mode",
                            "in": "query",
                            "required": False,
                            "schema": {"type": "string", "enum": ["relative", "absolute"], "default": "relative"},
                            "description": "relative uses minutes; absolute requires both start and end",
                        },
                        {
                            "name": "minutes",
                            "in": "query",
                            "required": False,
                            "schema": {"type": "integer", "minimum": 1, "default": 15},
                            "description": "Fallback window size in minutes (used when start/end are not provided)",
                        },
                        {
                            "name": "start",
                            "in": "query",
                            "required": False,
                            "schema": {"type": "string", "format": "date-time"},
                            "description": "Optional range start (ISO 8601)",
                        },
                        {
                            "name": "end",
                            "in": "query",
                            "required": False,
                            "schema": {"type": "string", "format": "date-time"},
                            "description": "Optional range end (ISO 8601); defaults to now when omitted",
                        },
                    ],
                    "responses": {
                        "200": {
                            "description": "Metric series",
                            "content": {
                                "application/json": {
                                    "example": {
                                        "metric": "cpu_percent",
                                        "series": [
                                            {
                                                "name": "cpu_percent",
                                                "labels": {"host": "node-1"},
                                                "points": [
                                                    {
                                                        "timestamp": "2026-04-19T16:00:00+00:00",
                                                        "value": 12.5,
                                                    }
                                                ],
                                            }
                                        ],
                                        "start": "2026-04-19T15:45:00+00:00",
                                        "end": "2026-04-19T16:00:00+00:00",
                                        "window_minutes": 15,
                                    }
                                }
                            },
                        },
                        "400": {
                            "description": "Invalid query",
                            "content": {
                                "application/json": {
                                    "example": {"error": "metric query parameter is required"}
                                }
                            },
                        },
                    },
                }
            },
            "/api/push": {
                "post": {
                    "summary": "Push a metric",
                    "requestBody": {
                        "required": True,
                        "content": {
                            "application/json": {
                                "example": {
                                    "name": "cpu_percent",
                                    "value": 10.0,
                                    "labels": {"source": "test"},
                                }
                            }
                        },
                    },
                    "responses": {
                        "201": {
                            "description": "Metric ingested",
                            "content": {
                                "application/json": {
                                    "example": {
                                        "status": "ok",
                                        "added": {
                                            "name": "cpu_percent",
                                            "labels": {"source": "test", "method": "push"},
                                            "timestamp": "2026-04-19T16:00:00+00:00",
                                            "value": 10.0,
                                        },
                                    }
                                }
                            },
                        },
                        "400": {
                            "description": "Invalid payload",
                            "content": {
                                "application/json": {
                                    "example": {"error": "Invalid payload"}
                                }
                            },
                        },
                        "503": {
                            "description": "Push API disabled",
                            "content": {
                                "application/json": {
                                    "example": {"error": "push api is disabled"}
                                }
                            },
                        },
                    },
                }
            },
            "/api/reload": {
                "post": {
                    "summary": "Reload runtime configuration from the active config file",
                    "responses": {
                        "200": {
                            "description": "Configuration reloaded successfully",
                            "content": {
                                "application/json": {
                                    "example": {
                                        "status": "ok",
                                        "config_path": "examples/config.example.yaml",
                                        "pull_targets": 1,
                                        "federate_refresh_seconds": 15,
                                        "log_level": "INFO",
                                    }
                                }
                            },
                        },
                        "400": {
                            "description": "Reload failed and previous config kept",
                            "content": {
                                "application/json": {
                                    "example": {
                                        "status": "error",
                                        "error": "Config file root must be a YAML object",
                                        "config_path": "examples/config.example.yaml",
                                    }
                                }
                            },
                        },
                    },
                }
            },
            "/federate": {
                "get": {
                    "summary": "Get latest federated sample per series",
                    "responses": {
                        "200": {
                            "description": "Federated snapshot",
                            "content": {
                                "application/json": {
                                    "example": {
                                        "metrics": [
                                            {
                                                "name": "cpu_percent",
                                                "labels": {"host": "node-1", "method": "scrape"},
                                                "value": 7.1,
                                            }
                                        ],
                                        "refreshed_at": "2026-04-19T16:00:00+00:00",
                                    }
                                }
                            },
                        }
                    },
                }
            },
            "/debug/populate": {
                "get": {
                    "summary": "Populate debug sample metrics",
                    "responses": {
                        "200": {
                            "description": "Debug data generated",
                            "content": {
                                "text/plain": {
                                    "example": "Debug population completed."
                                }
                            },
                        }
                    },
                }
            },
            "/api/explorer": {
                "get": {
                    "summary": "List metric catalog for autocomplete",
                    "responses": {
                        "200": {
                            "description": "Catalog response",
                            "content": {
                                "application/json": {
                                    "example": {
                                        "metrics": [
                                            {
                                                "name": "cpu_percent",
                                                "series_count": 1,
                                                "points_count": 42,
                                                "label_keys": ["host"],
                                                "label_samples": [{"host": "node-1"}],
                                                "last_seen": "2026-04-19T16:00:00+00:00",
                                                "last_value": 12.5,
                                                "freshness_seconds": 3
                                            }
                                        ]
                                    }
                                }
                            },
                        }
                    }
                }
            },
        },
    }