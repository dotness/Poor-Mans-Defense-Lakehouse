import os
import sys
from pathlib import Path
from dataclasses import dataclass
from dotenv import load_dotenv

# Ensure root and src are on sys.path
root_dir = Path(__file__).resolve().parent.parent.parent
src_dir = root_dir / "src"
for p in (str(root_dir), str(src_dir)):
    if p not in sys.path:
        sys.path.insert(0, p)

env_path = root_dir / ".env"
if env_path.exists():
    load_dotenv(dotenv_path=env_path)
else:
    load_dotenv()


@dataclass(frozen=True)
class Settings:
    # Environment
    env: str = os.getenv("ARTEMIS_ENV", "development")

    # AI & Google AI Studio
    google_api_key: str = os.getenv("GOOGLE_AI_STUDIO_API_KEY", "")
    gemini_model: str = os.getenv("GEMINI_MODEL", "gemini-2.5-flash-lite")

    # MQTT & Buffering
    mqtt_host: str = os.getenv("MQTT_BROKER_HOST", "localhost")
    mqtt_port: int = int(os.getenv("MQTT_BROKER_PORT", "1883"))
    mqtt_topic_prefix: str = os.getenv("MQTT_TOPIC_PREFIX", "telemetry")
    disk_buffer_dir: str = os.getenv("DISK_BUFFER_DIR", "/tmp/artemis/buffer")

    # MinIO
    minio_endpoint: str = os.getenv("MINIO_ENDPOINT", "localhost:9000")
    minio_access_key: str = os.getenv("MINIO_ACCESS_KEY", "minioadmin")
    minio_secret_key: str = os.getenv("MINIO_SECRET_KEY", "minioadmin")
    minio_bucket: str = os.getenv("MINIO_BUCKET", "telemetry")
    minio_use_ssl: bool = os.getenv("MINIO_USE_SSL", "false").lower() in ("true", "1", "yes")

    # PostgreSQL
    postgres_host: str = os.getenv("POSTGRES_HOST", "localhost")
    postgres_port: int = int(os.getenv("POSTGRES_PORT", "5433"))
    postgres_db: str = os.getenv("POSTGRES_DB", "artemis")
    postgres_user: str = os.getenv("POSTGRES_USER", "artemis")
    postgres_password: str = os.getenv("POSTGRES_PASSWORD", "artemis_secure_password")

    # Redis
    redis_host: str = os.getenv("REDIS_HOST", "localhost")
    redis_port: int = int(os.getenv("REDIS_PORT", "6379"))
    redis_db: int = int(os.getenv("REDIS_DB", "0"))

    # Memgraph
    memgraph_host: str = os.getenv("MEMGRAPH_HOST", "localhost")
    memgraph_port: int = int(os.getenv("MEMGRAPH_PORT", "7687"))
    memgraph_user: str = os.getenv("MEMGRAPH_USER", "")
    memgraph_password: str = os.getenv("MEMGRAPH_PASSWORD", "")

    # SpiderFoot
    spiderfoot_host: str = os.getenv("SPIDERFOOT_HOST", "localhost")
    spiderfoot_port: int = int(os.getenv("SPIDERFOOT_PORT", "5001"))

    # Traefik
    traefik_dashboard_port: int = int(os.getenv("TRAEFIK_DASHBOARD_PORT", "8088"))

    # Security & JWT
    jwt_secret_key: str = os.getenv("JWT_SECRET_KEY", "artemis_jwt_secret_super_secure_key_2026")
    jwt_algorithm: str = os.getenv("JWT_ALGORITHM", "HS256")
    jwt_expiration_minutes: int = int(os.getenv("JWT_EXPIRATION_MINUTES", "1440"))

    # Temporal Workflow Engine
    temporal_host: str = os.getenv("TEMPORAL_HOST", "localhost")
    temporal_port: int = int(os.getenv("TEMPORAL_PORT", "7233"))
    temporal_namespace: str = os.getenv("TEMPORAL_NAMESPACE", "default")

    # Observability & Langfuse
    langfuse_public_key: str = os.getenv("LANGFUSE_PUBLIC_KEY", "")
    langfuse_secret_key: str = os.getenv("LANGFUSE_SECRET_KEY", "")
    langfuse_host: str = os.getenv("LANGFUSE_HOST", "http://localhost:3000")

    # FastAPI Gateway
    api_host: str = os.getenv("API_HOST", "0.0.0.0")
    api_port: int = int(os.getenv("API_PORT", "8000"))

    # Docker Pipeline Runner (Feature 004)
    docker_runner_image: str = os.getenv("DOCKER_RUNNER_IMAGE", "artemis-pipeline-runner:latest")
    docker_run_timeout: int = int(os.getenv("DOCKER_RUN_TIMEOUT", "300"))
    docker_memory_limit: str = os.getenv("DOCKER_MEMORY_LIMIT", "2g")
    docker_cpu_limit: float = float(os.getenv("DOCKER_CPU_LIMIT", "2.0"))
    docker_runner_memory_limit: str = os.getenv("DOCKER_RUNNER_MEMORY_LIMIT", "2g")
    docker_runner_cpu_limit: float = float(os.getenv("DOCKER_RUNNER_CPU_LIMIT", "2.0"))
    pipeline_workspace_dir: str = os.getenv("PIPELINE_WORKSPACE_DIR", "/tmp/artemis/runs")

    # Knowledge Discovery Graph (Feature 005)
    discovery_sample_size: int = int(os.getenv("DISCOVERY_SAMPLE_SIZE", "10000"))
    discovery_entity_cap: int = int(os.getenv("DISCOVERY_ENTITY_CAP", "1000"))
    discovery_taxonomy_high_threshold: float = float(os.getenv("DISCOVERY_TAXONOMY_HIGH_THRESHOLD", "0.85"))
    discovery_taxonomy_low_threshold: float = float(os.getenv("DISCOVERY_TAXONOMY_LOW_THRESHOLD", "0.70"))
    discovery_fuzzy_threshold: float = float(os.getenv("DISCOVERY_FUZZY_THRESHOLD", "0.93"))
    discovery_lineage_depth: int = int(os.getenv("DISCOVERY_LINEAGE_DEPTH", "10"))
    discovery_retry_attempts: int = int(os.getenv("DISCOVERY_RETRY_ATTEMPTS", "3"))


settings = Settings()
