"""Owner-only migration, separate from deployment ZIP. Uses existing Azure CLI login.

Never prints an access token and never changes Azure identities or database grants.
"""
import argparse
import json
import re
import struct
import subprocess
import pyodbc
from sqlalchemy import create_engine
from sqlalchemy.engine import URL
from sqlalchemy.pool import NullPool
from foodsave.migrate import main as migrate


def add_connection_arguments(parser):
    parser.add_argument('--server', required=True)
    parser.add_argument('--database', required=True, choices=['foodsave'])
    parser.add_argument('--driver', required=True, choices=['ODBC Driver 18 for SQL Server','ODBC Driver 17 for SQL Server'])


def owner_database(server, driver):
    if not re.fullmatch(r'[a-zA-Z0-9-]+\.database\.windows\.net', server):
        raise ValueError('Expected an Azure SQL server hostname')
    if driver not in pyodbc.drivers():
        raise ValueError('Selected ODBC driver is not installed; no automatic installation is performed')
    # User must already have logged in as the existing authorized human owner.
    result = subprocess.run(['az','account','get-access-token','--resource','https://database.windows.net/','--output','json'], capture_output=True, text=True)
    if result.returncode:
        raise ValueError('Azure CLI token acquisition failed; verify the existing owner login privately')
    token = json.loads(result.stdout)['accessToken'].encode('utf-16-le')
    attrs = {1256: struct.pack('<I', len(token)) + token}
    connection = f'Driver={{{driver}}};Server=tcp:{server},1433;Database=foodsave;Encrypt=yes;TrustServerCertificate=no;Connection Timeout=10;'
    pyodbc.pooling = False
    database = create_engine(URL.create('mssql+pyodbc', query={'odbc_connect': connection}), connect_args={'attrs_before': attrs, 'timeout':10}, poolclass=NullPool, hide_parameters=True)
    return database


def main():
    parser = argparse.ArgumentParser()
    add_connection_arguments(parser)
    args = parser.parse_args()
    database = owner_database(args.server, args.driver)
    try:
        migrate(database)
    finally:
        database.dispose()
    print('FoodSave migrations completed. No runtime roles or grants were changed.')


if __name__ == '__main__':
    main()
