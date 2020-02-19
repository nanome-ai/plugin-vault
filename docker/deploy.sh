if [ "$(docker ps -aq -f name=vault)" != "" ]; then
    # cleanup
    echo "removing exited container"
    docker rm -f vault
fi

PORT=80
ARGS=$*

while [ "$1" != "" ]; do
    case $1 in
        -w)
            shift
            PORT=$1
            ;;
    esac
    shift
done

docker run -d \
--name vault \
--restart unless-stopped \
-p $PORT:$PORT \
-e ARGS="$ARGS" \
-v vault-volume:/root \
vault
