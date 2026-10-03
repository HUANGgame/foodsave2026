"""Run privately in App Service SSH; lists drivers only, no secrets or DB access."""
import json
import platform


def main():
    try:
        import pyodbc
        drivers = pyodbc.drivers()
        status = 'driver-present' if any(d in drivers for d in ('ODBC Driver 18 for SQL Server','ODBC Driver 17 for SQL Server')) else 'driver-missing'
    except ImportError:
        drivers, status = [], 'pyodbc-or-unixodbc-missing'
    print(json.dumps({'python': platform.python_version(), 'odbc_drivers': drivers, 'status': status}))


if __name__ == '__main__':
    main()
