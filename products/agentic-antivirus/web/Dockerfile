# Build context: products/agentic-antivirus (the console imports shared/i18n).
FROM node:22-alpine AS build
WORKDIR /src/web
COPY web/package.json web/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY shared /src/shared
COPY web ./
ARG NEXT_PUBLIC_BASE_PATH=/apps/agentic-antivirus
ARG NEXT_PUBLIC_API_BASE=/apps/agentic-antivirus/api
ARG NEXT_PUBLIC_ADS_ENABLED=false
ENV NEXT_PUBLIC_BASE_PATH=$NEXT_PUBLIC_BASE_PATH NEXT_PUBLIC_API_BASE=$NEXT_PUBLIC_API_BASE NEXT_PUBLIC_ADS_ENABLED=$NEXT_PUBLIC_ADS_ENABLED
RUN npx next build

FROM nginxinc/nginx-unprivileged:1.27-alpine
COPY deploy/nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /src/web/out /usr/share/nginx/html
COPY monetization/app-ads.txt /usr/share/nginx/html/app-ads.txt
EXPOSE 8080
