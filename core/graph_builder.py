import os

def load_and_apply_filters(graph_data, db_path):
    """Загружает фильтры с диска и возвращает отфильтрованный граф."""
    filter_state = {}
    for tab in ['keywords', 'ngrams', 'deputies', 'factions']:
        mode = False
        mf = os.path.join(db_path, f"{tab}_mode.state")
        if os.path.exists(mf):
            try:
                with open(mf, 'r') as f:
                    mode = f.read().strip().lower() == 'true'
            except:
                pass
        sel = set()
        bf = os.path.join(db_path, f"{tab}_blacklist.txt")
        if os.path.exists(bf):
            try:
                with open(bf, 'r') as f:
                    sel = {l.strip().split('\t')[0] for l in f if l.strip()}
            except:
                pass
        filter_state[tab] = {"mode": mode, "selected": sel}

    nodes_by_type = {"keyword": set(), "ngram": set(), "subject": set(), "faction": set()}
    for n in graph_data["nodes"]: nodes_by_type[n["type"]].add(n["id"])

    allowed = set(nodes_by_type["keyword"]) | set(nodes_by_type["ngram"]) | set(nodes_by_type["subject"]) | set(
        nodes_by_type["faction"])

    # 1. Применяем белые списки (сужаем до выбранного)
    if filter_state["deputies"]["mode"]: allowed &= (
                filter_state["deputies"]["selected"] | nodes_by_type["faction"] | nodes_by_type["keyword"])
    if filter_state["factions"]["mode"]:
        allowed &= filter_state["factions"]["selected"]
        # Если фракция в белом списке, оставляем только её депутатов
        fac_deputies = {n for n in nodes_by_type["subject"] if
                        any(e["source"] == n and e["type"] == "sub-fac" for e in graph_data["edges"])}
        allowed &= (fac_deputies | filter_state["factions"]["selected"] | nodes_by_type["keyword"])
    if filter_state["keywords"]["mode"]: allowed &= (
                filter_state["keywords"]["selected"] | nodes_by_type["subject"] | nodes_by_type["faction"])

    # 2. Применяем чёрные списки (удаляем выбранное)
    for cat in ["deputies", "factions", "keywords"]:
        if not filter_state[cat]["mode"]:
            allowed -= filter_state[cat]["selected"]
            if cat == "factions":  # Удаляем депутатов чёрной фракции
                rem_deps = {n["id"] for n in graph_data["nodes"] if n["type"] == "subject" and any(
                    e["target"] == n["id"] and e["source"] in filter_state["factions"]["selected"] for e in
                    graph_data["edges"])}
                allowed -= rem_deps

    # 3. Оставляем только рёбра между разрешёнными узлами
    f_nodes = [n for n in graph_data["nodes"] if n["id"] in allowed]
    f_edges = [e for e in graph_data["edges"] if e["source"] in allowed and e["target"] in allowed]
    return {"nodes": f_nodes, "edges": f_edges}