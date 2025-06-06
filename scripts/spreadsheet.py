import json
import os
import warnings
from io import BytesIO
from typing import Any

import yaml
from openpyxl import load_workbook
import requests
from openpyxl.worksheet.worksheet import Worksheet
import rfc3987

FLATTEN_CATALOG_HIERARCHY = False
CATALOG_BASE_URI = 'urn:ogc:defs/'


def load_worksheet(ws: Worksheet) -> list[dict[str, Any]]:
    headings = None
    result = []
    for i, row in enumerate(ws.rows):
        if i == 0:
            headings = [c.value for c in row if c.value is not None]
            continue
        if not row or row[0].value is None:
            continue
        result.append(dict(zip(headings, (cell.value for i, cell in enumerate(row)
                                          if i < len(headings)))))
    return result


def _main():
    secrets = json.loads(os.environ.get('ALL_SECRETS', '{}'))
    gsp_urls = {k.lower().replace('sparql_gsp_', ''): v
                 for k, v in secrets.items()
                 if k.lower().startswith('sparql_gsp_')}

    spreadsheet_url = os.environ.get('SPREADSHEET_URL')
    if not spreadsheet_url:
        raise Exception('SPREADSHEET_URL environment variable is not set')

    response = requests.get(spreadsheet_url)
    response.raise_for_status()

    with warnings.catch_warnings(action='ignore', category=UserWarning):
        wb = load_workbook(filename=BytesIO(response.content), read_only=True)

    with open('namespaces.yml') as f:
        namespaces = [{'prefix': p, 'uri': u} for p, u in yaml.safe_load(f).get('namespaces', {}).items()]

    for service in ('defs', 'defs-dev'):
        catalogs = load_worksheet(wb[f"{service}-collections"])
        mappings = load_worksheet(wb[f"{service}"])

        catalogs_by_uri = {catalog['URIFragment']: catalog for catalog in catalogs}
        catalogs_by_label = {catalog['Label']: catalog for catalog in catalogs}

        output = {
            '@context': {
                'dcat': 'http://www.w3.org/ns/dcat#',
                'skos': 'http://www.w3.org/2004/02/skos/core#',
                'dct': 'http://purl.org/dc/terms/',
                'vann': 'http://purl.org/vocab/vann/',
                'label': 'skos:prefLabel',
                'hasPart': {
                    '@id': 'dct:hasPart',
                    '@type': '@id',
                },
                'prefix': 'vann:preferredNamespacePrefix',
                'uri': 'vann:preferredNamespaceUri',
            },
            '@graph': [],
        }
        output['@graph'].extend(namespaces)

        for catalog in catalogs:
            parent_catalog = catalog.get('Parent')

            catalog_uri = catalog['URIFragment']

            if not rfc3987.match(catalog_uri, rule='absolute_URI'):
                root_catalog = catalog
                while root_catalog.get('Parent'):
                    root_catalog = catalogs_by_uri[root_catalog['Parent']]
                    catalog_uri = root_catalog['URIFragment'] + '/' + catalog_uri

                catalog_uri = CATALOG_BASE_URI + catalog_uri

            catalog['URI'] = catalog_uri

            if not FLATTEN_CATALOG_HIERARCHY or not parent_catalog:
                catalog_resource = {
                    '@id': catalog_uri,
                    '@type': 'dcat:TopCatalog' if not parent_catalog else 'dcat:Catalog',
                    'label': catalog['Label'],
                }
                if parent_catalog:
                    parent_catalog_resource = catalogs_by_uri[parent_catalog]['resource']
                    parent_catalog_resource.setdefault('hasPart', []).append(catalog_uri)
                catalog['resource'] = catalog_resource
                output['@graph'].append(catalog_resource)

        for mapping in mappings:
            if not mapping.get('Catalog'):
                continue
            catalog = catalogs_by_label[mapping['Catalog']]

            if FLATTEN_CATALOG_HIERARCHY:
                # Flatten catalog hierarchy - only use top level
                while catalog.get('Parent'):
                    catalog = catalogs_by_uri[catalog['Parent']]

            catalog['resource'].setdefault('hasPart', []).append(mapping['Concept Scheme'])

        with open(f'catalogs-{service}.jsonld', 'w') as f:
            json.dump(output, f, indent=2)

        gsp_url = gsp_urls.get(service.lower())
        if gsp_url:
            print(f"Found GSP configuration for {service}. Pushing data...")
            r = requests.put(gsp_url, json=output, headers={'Content-type': 'application/ld+json'})
            r.raise_for_status()
            print("Push OK")


if __name__ == '__main__':
    _main()
