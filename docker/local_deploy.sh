if [ "$(docker ps -aq -f name=vault)" != "" ]; then
        # cleanup
        echo "removing exited container"
        docker rm -f vault
fi

if [ "$1" != "" ]; then
    echo "Using specified plugin server: $1"
    docker run -d \
    -p 8888:8888 \
    -e PLUGIN_SERVER=$1 \
    --mount source=vault-volume,destination=/app \
    --name vault vault
else
    echo "Using default plugin server: plugins.nanome.ai"
    docker run -d \
    -p 8888:8888 \
    --mount source=vault-volume,destination=/app \
    --name vault vault
fi