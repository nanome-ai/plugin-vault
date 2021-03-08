FROM node:10-alpine

ENV ARGS=''

WORKDIR /app

COPY yarn.lock package.json ./
RUN yarn install --production
COPY . .

EXPOSE 80 443

CMD yarn start ${ARGS}
