FROM python:3.7

ENV PLUGIN_SERVER=plugins.nanome.ai

COPY . /app
WORKDIR /app

RUN pip install pycryptodome
RUN pip install nanome

CMD python -m nanome_vault.Vault -a ${PLUGIN_SERVER}