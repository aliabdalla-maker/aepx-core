FROM node:22-alpine AS build
WORKDIR /app
COPY package*.json ./
RUN npm install --no-audit --no-fund
COPY . .
RUN npm run build

FROM node:22-alpine
ENV NODE_ENV=production
WORKDIR /app
RUN addgroup -S aepx && adduser -S aepx -G aepx
COPY --from=build --chown=aepx:aepx /app ./
USER aepx
EXPOSE 3000
CMD ["npm","run","start","--","-H","0.0.0.0"]
