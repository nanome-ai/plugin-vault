FROM continuumio/miniconda3

ENV ARGS=''

RUN conda install -c openbabel openbabel
RUN pip install pycryptodome

ARG CACHEBUST
RUN pip install nanome

COPY . /app
WORKDIR /app

CMD python run.py ${ARGS}
