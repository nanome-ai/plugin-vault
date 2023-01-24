FROM node:16-alpine

ENV ARGS=''

ENV WORKDIR=/app
WORKDIR ${WORKDIR}

COPY server/yarn.lock server/package.json ./
RUN yarn install --production
COPY server .
RUN cd ui && yarn install && yarn build

RUN mkdir -p ${WORKDIR}/Documents/nanome-vault
RUN mkdir -p ${WORKDIR}/Documents/shared
EXPOSE 5000 5001

CMD yarn start ${ARGS}
