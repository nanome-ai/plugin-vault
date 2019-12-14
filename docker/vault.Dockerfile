FROM python:3.7

COPY . /app
WORKDIR /app
RUN pip install nanome
RUN pip install urllib3

CMD ["python", "-m", "nanome_vault.Vault", "-a", "192.168.1.116"]