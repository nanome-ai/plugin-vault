FROM nanome/plugin-env

ENV ARGS=''
WORKDIR /app

RUN apt-get update &&\
  apt-get install --no-install-recommends -y libgl1 libgomp1 &&\
  rm -rf /var/lib/apt/lists/*

ARG CACHEBUST
COPY requirements.txt .
RUN pip install -r requirements.txt

COPY . .

CMD python run.py ${ARGS}
