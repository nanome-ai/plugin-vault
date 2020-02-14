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
--restart always \
-p 8888:8888 \
-p $PORT:$PORT \
-e ARGS="$ARGS" \
-v vault-volume:/root \
--name vault vault
