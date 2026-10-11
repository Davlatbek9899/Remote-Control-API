import psycopg2
from psycopg2.extras import RealDictCursor

DB_CONFIG = {
    "dbname": "remotecontrol_db",
    "user": "rc_user",
    "password": "rc_password123",
    "host": "localhost",
    "port": 5432
}

def get_connection():
    return psycopg2.connect(**DB_CONFIG, cursor_factory=RealDictCursor)
