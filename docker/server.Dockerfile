FROM node:10-alpine

ENV ARGS=''

WORKDIR /app

COPY yarn.lock package.json ./
RUN yarn install --production
COPY . .

EXPOSE 80 443

ENV NO_PROXY vault-converter

CMD yarn start ${ARGS}
