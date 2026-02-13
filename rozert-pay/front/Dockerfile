# build and run webpack
FROM node:18.16 AS frontend-release

WORKDIR /app/src

COPY package.json package-lock.json /app/src/
COPY . /app/src

CMD ["bash", "-c", "npm install && npm run dev"]
