"""
Phase 12: Neo4j Driver & Connection Pool Manager

Provides a thread-safe connection pool singleton for Neo4j graph operations,
with health checks and graceful degradation fallback when Neo4j is offline.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional, Generator
from contextlib import contextmanager

try:
    from neo4j import GraphDatabase, Driver, Session, exceptions as neo4j_exceptions
    HAS_NEO4J_DRIVER = True
except ImportError:
    HAS_NEO4J_DRIVER = False
    Driver = Any
    Session = Any
    neo4j_exceptions = None

from app.config.settings import settings

logger = logging.getLogger(__name__)


class Neo4jConnectionManager:
    _instance: Optional[Neo4jConnectionManager] = None
    _driver: Optional[Driver] = None

    def __new__(cls) -> Neo4jConnectionManager:
        if cls._instance is None:
            cls._instance = super(Neo4jConnectionManager, cls).__new__(cls)
            cls._instance._init_driver()
        return cls._instance

    def _init_driver(self) -> None:
        if not HAS_NEO4J_DRIVER:
            logger.warning("neo4j Python package is not installed. Neo4j operations will run in mock/disabled mode.")
            self._driver = None
            return

        if not settings.neo4j_enabled:
            logger.info("Neo4j integration is disabled via configuration settings.")
            self._driver = None
            return

        try:
            auth = (settings.neo4j_user, settings.neo4j_password)
            self._driver = GraphDatabase.driver(
                settings.neo4j_uri,
                auth=auth,
                max_connection_lifetime=3600,
                max_connection_pool_size=50,
                connection_acquisition_timeout=10.0,
            )
            logger.info(f"Neo4j driver initialized successfully for {settings.neo4j_uri}")
        except Exception as e:
            logger.error(f"Failed to initialize Neo4j driver: {e}")
            self._driver = None

    def get_driver(self) -> Optional[Driver]:
        if self._driver is None and HAS_NEO4J_DRIVER and settings.neo4j_enabled:
            self._init_driver()
        return self._driver

    def is_healthy(self) -> bool:
        """Check if Neo4j instance is reachable and responsive."""
        driver = self.get_driver()
        if driver is None:
            return False

        try:
            driver.verify_connectivity()
            return True
        except Exception as e:
            logger.warning(f"Neo4j health check failed: {e}")
            return False

    @contextmanager
    def session(self) -> Generator[Optional[Session], None, None]:
        """Provide a managed Neo4j session context."""
        driver = self.get_driver()
        if driver is None:
            yield None
            return

        session = None
        try:
            session = driver.session(database=settings.neo4j_database)
            yield session
        except Exception as e:
            logger.error(f"Neo4j session error: {e}")
            yield None
        finally:
            if session is not None:
                try:
                    session.close()
                except Exception:
                    pass

    def execute_write(self, query: str, parameters: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
        """Execute a write Cypher query safely within a transaction."""
        parameters = parameters or {}
        with self.session() as sess:
            if sess is None:
                raise RuntimeError("Neo4j driver session unavailable")
            result = sess.execute_write(lambda tx: tx.run(query, parameters).data())
            return result or []

    def execute_read(self, query: str, parameters: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
        """Execute a read Cypher query safely within a transaction."""
        parameters = parameters or {}
        with self.session() as sess:
            if sess is None:
                raise RuntimeError("Neo4j driver session unavailable")
            result = sess.execute_read(lambda tx: tx.run(query, parameters).data())
            return result or []

    def close(self) -> None:
        if self._driver is not None:
            try:
                self._driver.close()
                logger.info("Neo4j driver closed.")
            except Exception as e:
                logger.warning(f"Error closing Neo4j driver: {e}")
            finally:
                self._driver = None


neo4j_manager = Neo4jConnectionManager()
