import asyncpg
import sys
from typing import Optional
from src.common.config import CRDB_CONFIG


class CockroachConnectionPool:
    _instance: Optional[asyncpg.Pool] = None
    dsn: str = ""

    @classmethod
    async def get_connection_pool(cls) -> asyncpg.Pool:
        database_url = create_default_url()
        if cls._instance is None:
            try:
                cls._instance = await asyncpg.create_pool(
                    database_url,
                    min_size=5,
                    max_size=20,
                    command_timeout=60
                )   
                cls.dsn = database_url
            except Exception as e:
                print(f"Cannot create connection pool: {e}", file=sys.stderr)
                raise
            
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
                cls.dsn = database_url
        except Exception as e:
            print(f"Cannot create connection pool: {e}", file=sys.stderr)
            raise

        return cls._instance
    
    @classmethod
    async def close(cls):
        if cls._instance:
            await cls._instance.close()
            cls.dsn = ""


def create_default_url() -> str :
    url = f'''postgresql://{CRDB_CONFIG["username"]}@{CRDB_CONFIG["host"]}:{CRDB_CONFIG["port"]}/{CRDB_CONFIG["database"]}'''    
    if CRDB_CONFIG["password"]:
        url += f'''?password={CRDB_CONFIG["password"]}'''

    if CRDB_CONFIG["ssl_mode"] and CRDB_CONFIG["ssl_mode"] != 'disable':
        url += f'''&sslmode={CRDB_CONFIG["ssl_mode"]}&sslrootcert={CRDB_CONFIG["ssl_ca_cert"]}&sslcert={CRDB_CONFIG["ssl_cert"]}&sslkey={CRDB_CONFIG["ssl_key"]}'''

    return url

def create_url(host: str, port: int, database: str, username: str, password: str, 
                                sslmode: str, sslcert: str, sslkey: str, sslrootcert: str) -> str:
    
    url = f'''postgresql://{username}@{host}:{port}/{database}'''    
    if password:
        url += f'''?password={password}'''

    if sslmode != 'disable':
        url += f'''&sslmode={sslmode}&sslrootcert={sslrootcert}&sslcert={sslcert}&sslkey={sslkey}'''
        url += f'''&sslmode={sslmode}'''
    
    return url
