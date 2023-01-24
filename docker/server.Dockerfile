FROM node:16-alpine

ENV ARGS=''

WORKDIR /app

COPY server/yarn.lock server/package.json ./
RUN yarn install --production
COPY server .
RUN cd ui && yarn install && yarn build
RUN mkdir -p /app/Documents/nanome-vault
RUN mkdir -p /app/Documents/shared
RUN chmod +w -R /app/Documents
EXPOSE 80 443

CMD yarn start ${ARGS}
