FROM nanome/plugin-env

ENV ARGS=''
WORKDIR /app

ARG CACHEBUST
COPY requirements.txt .
RUN pip install -r requirements.txt

COPY . .

ENV NO_PROXY vault-server

CMD python run.py ${ARGS}
