FROM node:20-alpine AS build

WORKDIR /app

COPY package*.json /app/
RUN npm install --legacy-peer-deps

COPY . /app
RUN npm run build

FROM nginx:1.27-alpine

COPY --from=build nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /app/dist /usr/share/nginx/html

EXPOSE 3000

CMD ["nginx", "-g", "daemon off;"]