FROM node:10-alpine

ENV ARGS=''

WORKDIR /app

COPY server/yarn.lock server/package.json ./
RUN yarn install --production
COPY server .
RUN cd ui && yarn install && yarn build

EXPOSE 80 443

CMD yarn start ${ARGS}
