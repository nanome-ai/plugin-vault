#!/bin/bash

echo "./deploy.sh $*" > redeploy.sh
chmod +x redeploy.sh

if [ "$(docker ps -aq -f name=vault)" != "" ]; then
    echo "removing exited container"
    docker rm -f vault
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

PORT=80
ARGS=$*

while [ "$1" != "" ]; do
    case $1 in
        -w | --web-port )
            shift
            PORT=$1
            ;;
    esac
    shift
done

docker run -d \
--name vault \
--restart unless-stopped \
--network vault-network \
-p $PORT:$PORT \
-e ARGS="$ARGS" \
-v vault-volume:/root \
vault
