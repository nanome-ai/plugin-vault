#!/bin/bash

echo "./deploy.sh $*" > redeploy.sh
chmod +x redeploy.sh

if [ -z "$(docker network ls -qf name=vault-network)" ]; then
    echo "creating network"
    docker network create --driver bridge vault-network
fi

existing=$(docker ps -aqf name='vault(-server)?$')
if [ -n "$existing" ]; then
    echo "removing existing container(s)"
    docker rm -f $existing
fi

if [ -z "$(docker ps -qf name=vault-converter)" ]; then
    echo "starting vault-converter"
    docker run -d \
    --name vault-converter \
    --network vault-network \
    --restart unless-stopped \
    --env DISABLE_GOOGLE_CHROME=1 \
    --env MAXIMUM_WAIT_TIMEOUT=60 \
    --env DEFAULT_WAIT_TIMEOUT=60 \
    thecodingmachine/gotenberg:6 2>&1
fi

# NGINX and SERVER_ARGS used for jwilder/nginx-proxy config
NGINX=0
PORT_SET=0
SERVER_ARGS=()
DEFAULT_PORT=80
SERVER_PORT=80
PORT=
ARGS=$*

# generate random hex api key
API_KEY=`od -vN "16" -An -tx1 /dev/urandom | tr -d " \n"`

while [ -n "$1" ]; do
    case $1 in
        --https | -s | --ssl-cert )
            if [ -z "$PORT" ]; then
                PORT=443
            fi
            SERVER_PORT=443
            SERVER_ARGS+=(
                --env CERT_NAME=default
                --env VIRTUAL_PORT=443
                --env VIRTUAL_PROTO=https
            )
            ;;
        --nginx )
            NGINX=1
            ;;
        -u | --url )
            SERVER_ARGS+=(--env VIRTUAL_HOST=$2)
            shift
            ;;
        -w | --web-port )
            PORT=$2
            PORT_SET=1
            shift
            ;;
    esac
    shift
done

if [ -z "$PORT" ]; then
    PORT=$DEFAULT_PORT
elif [ $NGINX -eq 1 ] && [ $PORT_SET -eq 1 ]; then
    echo "Error: --nginx and -w/--web-port are mutually exclusive"
    exit 1
fi

# bind port if not using nginx proxy
if [ $NGINX -eq 0 ]; then
    SERVER_ARGS+=(-p $PORT:$SERVER_PORT)
fi

plugin_container_name="vault"
server_container_name="vault-server"

docker run -d \
--name $plugin_container_name \
--network vault-network \
--restart unless-stopped \
-h $(hostname)-$plugin_container_name \
--env no_proxy=$server_container_name \
--env NO_PROXY=$server_container_name \
-e ARGS="$ARGS --api-key $API_KEY" \
$plugin_container_name

docker run -d \
--name $server_container_name \
--network vault-network \
--restart unless-stopped \
--env no_proxy=vault-converter \
--env NO_PROXY=vault-converter \
${SERVER_ARGS[@]} \
-e ARGS="$ARGS --api-key $API_KEY" \
-v vault-volume:/root \
$server_container_name
