#!/bin/bash

echo "./deploy.sh $*" > redeploy.sh
chmod +x redeploy.sh

if [ "$(docker ps -aq -f name=vault)" != "" ]; then
    echo "removing exited container"
    docker rm -f vault
fi

if [ "$(docker ps -aq -f name=vault-server)" != "" ]; then
    echo "removing exited container"
    docker rm -f vault-server
fi

if [ "$(docker network ls -qf name=vault-network)" == "" ]; then
    echo "creating network"
    docker network create --driver bridge vault-network
fi

if [ "$(docker ps -qf name=vault-converter)" == "" ]; then
    echo "starting vault-converter"
    docker run --rm -d \
    --name vault-converter \
    --network vault-network \
    --env DISABLE_GOOGLE_CHROME=1 \
    --env MAXIMUM_WAIT_TIMEOUT=60 \
    --env DEFAULT_WAIT_TIMEOUT=60 \
    thecodingmachine/gotenberg:6 2>&1
fi

DEFAULT_PORT=80
SERVER_PORT=80
PORT=
ARGS=$*

# generate random hex api key
API_KEY=`od -vN "16" -An -tx1 /dev/urandom | tr -d " \n"`

while [ "$1" != "" ]; do
    case $1 in
        --https | -s | --ssl-cert )
            if [ -z "$PORT" ]; then
                PORT=443
            fi
            SERVER_PORT=443
            ;;
        -w | --web-port )
            shift
            PORT=$1
            ;;
    esac
    shift
done

if [ -z "$PORT" ]; then
    PORT=$DEFAULT_PORT
fi

docker run -d \
--name vault \
--restart unless-stopped \
--network vault-network \
-e ARGS="$ARGS --api-key $API_KEY" \
vault

docker run -d \
--name vault-server \
--restart unless-stopped \
--network vault-network \
-p $PORT:$SERVER_PORT \
-e ARGS="$ARGS --api-key $API_KEY" \
-v vault-volume:/root \
vault-server
