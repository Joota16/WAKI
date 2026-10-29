"""Conectividad inicial. Las consultas de reportes se añadirán posteriormente."""

from app.db.database import Database


def check_connection(database: Database) -> bool:
    with database.connect() as connection:
        return connection.execute("SELECT 1").fetchone()[0] == 1

