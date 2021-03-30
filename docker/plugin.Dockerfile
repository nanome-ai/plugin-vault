FROM nanome/plugin-env

ENV ARGS=''

RUN pip install pycryptodome

ARG CACHEBUST
RUN pip install nanome

COPY . /app
WORKDIR /app

ENV NO_PROXY vault-server

CMD python run.py ${ARGS}
