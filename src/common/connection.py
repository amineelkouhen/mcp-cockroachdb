import asyncpg
import sys
from typing import Optional, Dict, List
from src.common.config import CRDB_CONFIG


class CockroachConnectionPool:
    _instance: Optional[asyncpg.Pool] = None
    database_url: str = ""
    current_database:str = ""
    query_history: List[Dict] = []

    @classmethod
    async def get_connection_pool(cls) -> asyncpg.Pool:
        url = create_default_url()
        if not cls._instance or cls._instance._closed:
            await cls.create_connection_pool(url)

        return cls._instance

    @classmethod
    async def refresh_connection_pool(cls, host: str, port: int, database: str, username: str, password: str, 
                                sslmode: str, sslcert: str, sslkey: str, sslrootcert: str) -> asyncpg.Pool:

        database_url = create_url(host, port, database, username, password, sslmode, sslcert, sslkey, sslrootcert)
        return await cls.create_connection_pool(database_url)

    @classmethod
    async def create_connection_pool(cls, database_url: str) -> asyncpg.Pool:
        try:
            if database_url:
                cls._instance = await asyncpg.create_pool(
                    database_url,
                    min_size=5,
                    max_size=20,
                    command_timeout=60
                )
                cls.database_url = database_url
                cls.current_database = extract_database(database_url)
        except Exception as e:
            print(f"Cannot create connection pool: {e}", file=sys.stderr)
            raise

        return cls._instance

    @classmethod
    async def close(cls):
        if cls._instance:
            await cls._instance.close()
            cls.database_url = ""
            cls.current_database = ""

def create_default_url() -> str:
    url = f'''postgresql://{CRDB_CONFIG["username"]}@{CRDB_CONFIG["host"]}:{CRDB_CONFIG["port"]}/{CRDB_CONFIG["database"]}'''
    query_params = []

    if CRDB_CONFIG["password"]:
        query_params.append(f'password={CRDB_CONFIG["password"]}')

    if CRDB_CONFIG["ssl_mode"] and CRDB_CONFIG["ssl_mode"] != 'disable':
        query_params.append(f'sslmode={CRDB_CONFIG["ssl_mode"]}')
        query_params.append(f'sslrootcert={CRDB_CONFIG["ssl_ca_cert"]}')
        query_params.append(f'sslcert={CRDB_CONFIG["ssl_cert"]}')
        query_params.append(f'sslkey={CRDB_CONFIG["ssl_key"]}')

    if query_params:
        url += '?' + '&'.join(query_params)

    return url

def create_url(host: str, port: int, database: str, username: str, password: str, 
                                sslmode: str, sslcert: str, sslkey: str, sslrootcert: str) -> str:
    
    url = f'''postgresql://{username}@{host}:{port}/{database}'''
    query_params = []

    if password:
        query_params.append(f'password={password}')

    if sslmode and sslmode != 'disable':
        query_params.append(f'sslmode={sslmode}')
        query_params.append(f'sslrootcert={sslrootcert}')
        query_params.append(f'sslcert={sslcert}')
        query_params.append(f'sslkey={sslkey}')

    if query_params:
        url += '?' + '&'.join(query_params)
    
    return url

def extract_database(database_url: str) -> str:
    dsn_parts = database_url.split('/')
    query = dsn_parts[-1]
    if "?" in query:
        database = query[:query.index("?")]
    else: 
        database = query
    
    return database
 