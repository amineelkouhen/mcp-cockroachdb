from dotenv import load_dotenv
import os
import urllib.parse

load_dotenv()

CRDB_CONFIG = {
             "host": os.getenv('CRDB_HOST', '127.0.0.1'),
             "port": int(os.getenv('CRDB_PORT', 00000)),
             "username": os.getenv('CRDB_USERNAME', 'root'),
             "password": os.getenv('CRDB_PWD', None),
             "database": os.getenv('CRDB_DATABASE', 'defaultdb'),
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
            config['database'] = parsed.path.lstrip('/')
        except ValueError:
            config['database'] = 'defaultdb'
    else:
        config['database'] = 'defaultdb'

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
