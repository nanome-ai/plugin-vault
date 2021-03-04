#!/bin/bash

if [[ $(docker volume ls -f name=vault-volume -q) ]]; then
    echo "Skipping volume creation"
else
    echo "Creating new docker volume"
    docker volume create vault-volume
fi

cachebust=0
while [ $# -gt 0 ]; do
  case $1 in
    -u | --update ) cachebust=1 ;;
  esac
  shift
done

if [ ! -f ".cachebust" ] || (($cachebust)); then
  date +%s > .cachebust
fi

cachebust=`cat .cachebust`
docker build -f plugin.Dockerfile --build-arg CACHEBUST=$cachebust -t vault:latest ..
docker build -f server.Dockerfile -t vault-server:latest ../server
