if [[ $(docker volume ls -f name=vault-volume -q) ]]; then
    echo "Skipping volume creation"
else
    echo "Creating new docker volume"
    docker volume create vault-volume
fi

docker build -f Dockerfile --build-arg CACHEBUST=$(date +%s) -t vault:latest ..
