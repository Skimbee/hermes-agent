FROM node:26-bookworm-slim@sha256:cd9f682fa2885cd1056e830424764158570061c59736a1da836bc3d73df095ae AS node
FROM python:3.11-slim-bookworm@sha256:528257d48c1da0dcecc2e725d1ae34498d60c965f1241e39cd6a85a8859bdf84
COPY --from=node /usr/local/bin/node /usr/local/bin/node
COPY --from=node /usr/local/lib/node_modules /usr/local/lib/node_modules
RUN ln -s ../lib/node_modules/npm/bin/npm-cli.js /usr/local/bin/npm && ln -s ../lib/node_modules/npm/bin/npx-cli.js /usr/local/bin/npx && apt-get update && apt-get install -y --no-install-recommends git build-essential curl ca-certificates procps socat && rm -rf /var/lib/apt/lists/* && pip install --no-cache-dir uv==0.12.13 && useradd --uid 10001 --create-home bridge && mkdir /work && chown 10001:10001 /work
ENV HOME=/work/home HERMES_HOME=/work/home/.hermes XDG_CONFIG_HOME=/work/home/config XDG_CACHE_HOME=/work/home/cache HERMES_NONINTERACTIVE=1 PATH=/work/client/.venv/bin:/usr/local/bin:/usr/bin:/bin
WORKDIR /work
USER 10001:10001
CMD ["python3","-I","-c","import time; time.sleep(7200)"]
