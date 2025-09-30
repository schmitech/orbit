#!/bin/bash

HOST="localhost"
PORT=27017

# Test with mongosh
if command -v mongosh &>/dev/null; then
    echo "Testing MongoDB connection with mongosh..."
    if mongosh --host $HOST --port $PORT --eval "db.adminCommand('ping')" &>/dev/null; then
        echo "[mongosh] Connection successful!"
    else
        echo "[mongosh] Connection failed!"
    fi
else
    echo "mongosh not found. Skipping mongosh test."
fi

# Test with mongo
if command -v mongo &>/dev/null; then
    echo "Testing MongoDB connection with mongo..."
    if mongo --host $HOST --port $PORT --eval "db.adminCommand('ping')" &>/dev/null; then
        echo "[mongo] Connection successful!"
    else
        echo "[mongo] Connection failed!"
    fi
else
    echo "mongo not found. Skipping mongo test."
fi

# Test with netcat
if command -v nc &>/dev/null; then
    echo "Testing MongoDB port with netcat..."
    if nc -z $HOST $PORT; then
        echo "[netcat] Port $PORT is open!"
    else
        echo "[netcat] Port $PORT is closed!"
    fi
else
    echo "netcat (nc) not found. Skipping netcat test."
fi 