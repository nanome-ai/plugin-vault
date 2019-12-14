if [[ $(docker volume inspect vault-volume) ]]; then
    echo "Skipping Vault volume creation"
else
    echo "Creating new docker volume for Vault"
    docker volume create vault-volume
fi

docker build -f vault.Dockerfile -t vault:latest ..