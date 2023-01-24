FROM node:16-alpine

ENV ARGS=''

WORKDIR /app

COPY server/yarn.lock server/package.json ./
RUN yarn install --production
COPY server .
RUN cd ui && yarn install && yarn build

# Done to allow writes in openshift deploys.
# Openshift runs containers as a random user, so we need to change the group
# of the folder to 0 (root) and give it write permissions.
# Also, in openshift, the home directory for root is /, but in other environments
# it is /root. So we need to create /Documents, but it's only used in openshift environments.
ENV DOCS_FOLDER=/Documents
RUN mkdir -p ${DOCS_FOLDER} && \
    chgrp -R 0 ${DOCS_FOLDER} && \
    chmod -R g=u ${DOCS_FOLDER}

EXPOSE 5000 5001

CMD yarn start ${ARGS}
