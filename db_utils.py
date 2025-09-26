import psycopg
import logging

log = logging.getLogger(__name__)

def table_exists(db_uri: str, table_name: str) -> bool:
    """Check if a table exists in the database"""
    try:
        with psycopg.connect(db_uri) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT EXISTS (SELECT FROM information_schema.tables WHERE table_name = %s)",
                    (table_name,)
                )
                return cur.fetchone()[0]
    except Exception as e:
        log.error(f"Error checking if table {table_name} exists: {e}")
        return False