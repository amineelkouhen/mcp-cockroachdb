from dotenv import load_dotenv
import os
import urllib.parse

load_dotenv()

CRDB_CONFIG = {
             "url": os.getenv('CRDB_URL', None),
             "host": os.getenv('CRDB_HOST', '127.0.0.1'),
             "port": int(os.getenv('CRDB_PORT', 26257)),
             "username": os.getenv('CRDB_USERNAME', 'root'),
             "password": os.getenv('CRDB_PWD', None),
             "db": os.getenv('CRDB_DATABASE', 'defaultdb'),
             "ssl_ca_cert": os.getenv('CRDB_SSL_CA_PATH', None),
             "ssl_key": os.getenv('CRDB_SSL_KEYFILE', None),
             "ssl_cert": os.getenv('CRDB_SSL_CERTFILE', None),
             "ssl_mode": os.getenv('CRDB_SSL_MODE', 'disable')}

def parse_crdb_uri(uri: str) -> dict:
    """Parse a CRDB URI and return connection parameters."""
    parsed = urllib.parse.urlparse(uri)

    config = {}

    # Check Scheme in URL
    if parsed.scheme not in ['cockroach', 'postgresql']:
        raise ValueError(f"Unsupported scheme: {parsed.scheme}")

    config['url'] = uri
    # Host and port
    config['host'] = parsed.hostname or '127.0.0.1'
    config['port'] = parsed.port or 26257

    # Database
    if parsed.path and parsed.path != '/':
        try:
            config['db'] = parsed.path.lstrip('/')
        except ValueError:
            config['db'] = 'defaultdb'
    else:
        config['db'] = 'defaultdb'

    # Authentication
    if parsed.username:
        config['username'] = parsed.username
    if parsed.password:
        config['password'] = parsed.password

    # Parse query parameters for SSL and other options
    if parsed.query:
        query_params = urllib.parse.parse_qs(parsed.query)

        # Handle SSL parameters
        if 'sslmode' in query_params:
            config['ssl_mode'] = query_params['sslmode'][0]
        if 'sslrootcert' in query_params:
            config['ssl_ca_cert'] = query_params['sslrootcert'][0]
        if 'sslcert' in query_params:
            config['ssl_cert'] = query_params['sslcert'][0]
        if 'sslkey' in query_params:
            config['ssl_key'] = query_params['sslkey'][0]

        #   The SQL user's password. It is not recommended to pass the password in the URL directly.
        if 'password' in query_params:
            try:
                config['password'] = query_params['password'][0]
            except ValueError:
                pass

    return config


def set_crdb_config_from_cli(config: dict):
    for key, value in config.items():
        if key == 'port':
            # Keep port as integer
            CRDB_CONFIG[key] = int(value)
        else:
            # Convert other values to strings
            CRDB_CONFIG[key] = str(value) if value is not None else None

    backfill_config()

def backfill_config():
    dns = ""
    if CRDB_CONFIG["url"] is None:
        dns = f'''postgresql://{CRDB_CONFIG["username"]}'''    
        if CRDB_CONFIG["password"]:
            dns += f''':{CRDB_CONFIG["password"]}@{CRDB_CONFIG["host"]}:{CRDB_CONFIG["port"]}/{CRDB_CONFIG["db"]}?sslmode={CRDB_CONFIG["ssl_mode"]}'''
        else:
            dns += f'''@{CRDB_CONFIG["host"]}:{CRDB_CONFIG["port"]}/{CRDB_CONFIG["db"]}?sslmode={CRDB_CONFIG["ssl_mode"]}'''

        if CRDB_CONFIG["ssl_mode"] != 'disable':
            dns += f'''&sslrootcert={CRDB_CONFIG["ssl_ca_cert"]}&sslcert={CRDB_CONFIG["ssl_cert"]}&sslkey={CRDB_CONFIG["ssl_key"]}'''

        CRDB_CONFIG["url"] = dns