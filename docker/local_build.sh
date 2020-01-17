if [[ $(docker volume ls -f name=vault-volume -q) ]]; then
    echo "Skipping volume creation"
else
    echo "Creating new docker volume"
    docker volume create vault-volume
fi

docker build -f vault.Dockerfile -t vault:latest ..