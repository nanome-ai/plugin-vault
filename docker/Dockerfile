FROM nanome/plugin-env

ENV ARGS=''

RUN pip install pycryptodome

ARG CACHEBUST
RUN pip install nanome

COPY . /app
WORKDIR /app

CMD python run.py ${ARGS}
