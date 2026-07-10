FROM nginx:1.30.3-alpine

COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY snippets/ /etc/nginx/snippets/
COPY . /usr/share/nginx/html

RUN chown -R nginx:nginx /usr/share/nginx/html /etc/nginx/conf.d /var/cache/nginx /run && \
    chmod -R g-w /usr/share/nginx/html /etc/nginx/conf.d

USER nginx

EXPOSE 80
