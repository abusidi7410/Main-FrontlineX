# Frontline Nexus — edge proxy with firewall-layer rate limiting.
#
# A slim Nginx that sits in front of the Django service. All API traffic is
# gated here (auth 5r/m, payments 10r/m, standard 60r/m per client IP) and
# rejected with 429 BEFORE reaching Django, so Python is never even hit.
#
# Build / run:
#   docker build -t frontlinex-edge -f nginx/Dockerfile nginx/
#   docker run --rm -e UPSTREAM_URL=host.docker.internal:8000 -p 80:80 frontlinex-edge
# or wire it via docker-compose.edge.yml.
FROM nginx:1.27-alpine

# The official image auto-templates /etc/nginx/templates/*.template → conf.d
# using envsubst; set UPSTREAM_URL at runtime, e.g. UPSTREAM_URL=backend:8000.
COPY conf.d/ /etc/nginx/templates/

EXPOSE 80