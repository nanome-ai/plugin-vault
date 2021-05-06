FROM node:10-alpine

ENV ARGS=''

WORKDIR /app

COPY server/yarn.lock server/package.json ./
RUN yarn install --production
COPY server .

EXPOSE 80 443

ENV NO_PROXY vault-converter

CMD yarn start ${ARGS}
