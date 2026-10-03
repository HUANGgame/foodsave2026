import os
from functools import lru_cache
from sqlalchemy import create_engine, text
from sqlalchemy.engine import URL
from sqlalchemy.pool import NullPool


@lru_cache
def engine(profile='runtime'):
    # Deployment supplies the secret. No fallback DB or auto schema creation.
    variable = {'runtime': 'FOODSAVE_ODBC_CONNECTION', 'viewer': 'FOODSAVE_VIEWER_ODBC_CONNECTION'}[profile]
    odbc = os.environ.get(variable)
    if not odbc and profile == 'runtime' and os.getenv('FOODSAVE_SQL_SERVER'):
        import pyodbc
        driver = os.getenv('FOODSAVE_ODBC_DRIVER', '')
        server = os.environ['FOODSAVE_SQL_SERVER']
        database = os.getenv('FOODSAVE_SQL_DATABASE', '')
        if database != 'foodsave' or not server.endswith('.database.windows.net') or any(c in server for c in ';{}'):
            raise RuntimeError('Dedicated foodsave database configuration required')
        if driver not in ('ODBC Driver 18 for SQL Server', 'ODBC Driver 17 for SQL Server') or driver not in pyodbc.drivers():
            raise RuntimeError('An installed and verified SQL Server ODBC driver is required')
        odbc = f'Driver={{{driver}}};Server=tcp:{server},1433;Database=foodsave;Authentication=ActiveDirectoryMsi;Encrypt=yes;TrustServerCertificate=no;Connection Timeout=10;'
    if not odbc:
        raise RuntimeError(variable + ' is required')
    import pyodbc
    pyodbc.pooling = False  # Release idle connections; do not defeat SQL auto-pause.
    return create_engine(URL.create('mssql+pyodbc', query={'odbc_connect': odbc}),
                         poolclass=NullPool, hide_parameters=True, echo=False,
                         connect_args={"timeout": 10})


def one(conn, sql, **params):
    return conn.execute(text(sql), params).mappings().first()


def rows(conn, sql, **params):
    return list(conn.execute(text(sql), params).mappings())


def execute(conn, sql, **params):
    return conn.execute(text(sql), params)
