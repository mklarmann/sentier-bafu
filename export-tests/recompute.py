"""Scores computed three ways, to compare what a file says with what Brightway computes.

`brightway` is the reference: stock matrices from the project, factored once.
`openlca` and `simapro` compute the same score from the exported file alone, as read
back by `olca_schema` and `bw_simapro_csv`, linking the way each format links
(openLCA by default provider, SimaPro by product name). They are a reading of the
files, not a run of openLCA or SimaPro.
"""

import numpy as np
from conftest import step


def brightway(project, database, method):
    """`{code: score}` for one unit of every activity; `method` is `[(flow key, factor)]`."""
    import bw2calc as bc
    import bw2data as bd

    bd.projects.set_current(project)
    nodes = list(bd.Database(database))
    lca = bc.LCA({nodes[0]: 1})
    lca.lci()
    factors = np.zeros(lca.biosphere_matrix.shape[0])
    for key, factor in method:
        row = lca.dicts.biosphere.get(bd.get_node(database=key[0], code=key[1]).id)
        if row is not None:
            factors[row] = factor
    # One factorisation serves every product: score = factors · B · A⁻¹.
    per_product = (
        factors @ lca.biosphere_matrix.toarray() @ np.linalg.inv(lca.technosphere_matrix.toarray())
    )
    return {node["code"]: float(per_product[lca.dicts.product[node.id]]) for node in nodes}


def _inverse(size, entries):
    technosphere = np.zeros((size, size))
    for row, column, amount in entries:
        technosphere[row, column] += amount
    return np.linalg.inv(technosphere)


def openlca(path, nodes, namespace, method):
    """`{code: score}` from the JSON-LD archive. A second product output gets no credit:
    the file gives it neither an allocation factor nor an avoided-product flag."""
    flow_id, process_id = step.olca_ids(namespace)
    archive = step.read_openlca(path)
    factors = {flow_id(key): factor for key, factor in method}
    index = {pid: i for i, pid in enumerate(archive["processes"])}
    entries, burdens, reference = [], np.zeros(len(index)), {}
    for pid, process in archive["processes"].items():
        for exchange in process.exchanges:
            # Amounts are in the exchange's unit; the factor takes them to the reference unit.
            unit = archive["units"][exchange.unit.id]
            amount = exchange.amount * unit.conversion_factor
            if exchange.is_quantitative_reference:
                entries.append((index[pid], index[pid], amount))
                reference[pid] = unit.conversion_factor
            elif exchange.default_provider is not None:
                entries.append((index[exchange.default_provider.id], index[pid], -amount))
            elif exchange.flow.id in factors:
                burdens[index[pid]] += factors[exchange.flow.id] * exchange.amount
    per_reference_unit = burdens @ _inverse(len(index), entries)
    return {
        key[1]: float(per_reference_unit[index[process_id(key)]] * reference[process_id(key)])
        for key, node in nodes.items()
        if not step.is_elementary(node)
    }


def simapro(path, nodes, method):
    """`{code: score}` from the CSV. Burdens follow the allocation share of the first
    product row. An input that names no single product makes every score that needs
    it `nan`."""
    csv = step.read_simapro(path)
    providers, _ = step.simapro_links(csv)
    factors = {}
    for key, factor in method:
        flow = nodes[key]
        factors[(flow["name"], (*flow["categories"], "")[1])] = factor
    index = {identifier: i for i, identifier in enumerate(csv["processes"])}
    entries, burdens, unlinked = [], np.zeros(len(index)), set()
    for identifier, process in csv["processes"].items():
        product = process["products"][0]
        share = product["allocation"] / 100
        entries.append((index[identifier], index[identifier], product["amount"]))
        for position, row in enumerate(process["inputs"]):
            provider = providers[(identifier, position)]
            if provider is None:
                unlinked.add(index[identifier])
            else:
                entries.append((index[provider], index[identifier], -row["amount"] * share))
        for row in process["elementary"]:
            factor = factors.get((row["name"], row["context"][1]), 0.0)
            burdens[index[identifier]] += factor * row["amount"] * share
    inverse = _inverse(len(index), entries)
    per_product = burdens @ inverse
    for column in range(len(index)):
        if any(inverse[row, column] for row in unlinked):
            per_product[column] = np.nan
    return {
        key[1]: float(per_product[index[f"{key[0]}|{key[1]}"]])
        for key, node in nodes.items()
        if not step.is_elementary(node)
    }
