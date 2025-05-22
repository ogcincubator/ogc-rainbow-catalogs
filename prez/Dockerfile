FROM ghcr.io/rdflib/prez:4

COPY custom-endpoints.ttl .

RUN export PREZ_SITE_PACKAGE=""$(python -c 'import prez; print(prez.__path__[0])')"" && \
    export DATA_ENDPOINTS_CUSTOM="${PREZ_SITE_PACKAGE}/reference_data/endpoints/data_endpoints_custom" && \
    mkdir -p "${DATA_ENDPOINTS_CUSTOM}" && \
    mv custom-endpoints.ttl ${DATA_ENDPOINTS_CUSTOM}/ogc.ttl
