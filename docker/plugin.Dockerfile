FROM nanome/plugin-env

ENV ARGS=''
WORKDIR /app

ARG CACHEBUST
COPY requirements.txt .
RUN pip install -r requirements.txt

COPY nanome_vault nanome_vault
COPY run.py .

CMD python run.py ${ARGS}
