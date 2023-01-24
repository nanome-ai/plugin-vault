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
# DO NOT MERGE INTO MASTER
docker build -f server.Dockerfile -t public.ecr.aws/h7r1e4h2/vault-server:openshift ..
docker push public.ecr.aws/h7r1e4h2/vault-server:openshift
