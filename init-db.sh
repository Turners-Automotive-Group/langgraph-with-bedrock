#!/bin/bash
set -e

# Create the database if it doesn't exist
psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" <<-EOSQL
    SELECT 'CREATE DATABASE "bedrock-agent-db"'
    WHERE NOT EXISTS (SELECT FROM pg_database WHERE datname = 'bedrock-agent-db')\gexec
EOSQL

echo "Database setup completed"