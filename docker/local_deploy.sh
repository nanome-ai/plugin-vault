docker run -d \
-p 8888:8888 \
--mount source=vault-volume,destination=/app \
--name local_vault vault