import logging
import duckdb
from typing import Optional

try:
    from src.config.settings import settings
except ImportError:
    from config.settings import settings

logger = logging.getLogger("artemis.analytics.duckdb")


class DuckDBClient:
    def __init__(
        self,
        endpoint: Optional[str] = None,
        access_key: Optional[str] = None,
        secret_key: Optional[str] = None,
        use_ssl: Optional[bool] = None,
    ):
        self.endpoint = endpoint or settings.minio_endpoint
        self.access_key = access_key or settings.minio_access_key
        self.secret_key = secret_key or settings.minio_secret_key
        self.use_ssl = use_ssl if use_ssl is not None else settings.minio_use_ssl

        self.conn = duckdb.connect(database=":memory:")
        self._configure_s3()

    def _configure_s3(self):
        try:
            self.conn.execute("INSTALL httpfs; LOAD httpfs;")
        except Exception as e:
            logger.debug(f"httpfs extension load note: {e}")

        try:
            self.conn.execute(f"SET s3_endpoint = '{self.endpoint}';")
            self.conn.execute(f"SET s3_access_key_id = '{self.access_key}';")
            self.conn.execute(f"SET s3_secret_access_key = '{self.secret_key}';")
            self.conn.execute(f"SET s3_use_ssl = {'true' if self.use_ssl else 'false'};")
            self.conn.execute("SET s3_url_style = 'path';")
            logger.info("DuckDB configured with MinIO S3 endpoint.")
        except Exception as e:
            logger.warning(f"Failed to set DuckDB S3 parameters: {e}")

    def query(self, sql: str):
        return self.conn.execute(sql)
