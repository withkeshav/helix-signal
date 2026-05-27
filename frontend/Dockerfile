FROM nginx:1.30.1-alpine

COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY . /usr/share/nginx/html

RUN chown -R nginx:nginx /usr/share/nginx/html /etc/nginx/conf.d && \
    chmod -R g-w /usr/share/nginx/html /etc/nginx/conf.d

USER nginx

EXPOSE 80
