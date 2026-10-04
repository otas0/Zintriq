"""Phase 4 creator-system primitives for Universal Builder.

Definitions stay project-scoped and instances only store their deliberate
differences.  Published revisions carry the same resources as the draft so
runtime resolution and rollback remain deterministic.
"""

from __future__ import annotations

import json
import logging
import re
from datetime import datetime
from uuid import uuid4

_log = logging.getLogger("app.universal_builder")


JSON_FIELDS = {
    "root_structure", "property_schema", "slots", "variants", "data_inputs",
    "events", "token_dependencies", "metadata", "overrides", "slot_content",
    "bindings", "responsive", "values_json", "value_json", "configuration",
}


def now():
    return datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")


def load_json(value, fallback):
    if isinstance(value, (dict, list, int, float, bool)) or value is None:
        return value if value is not None else fallback
    try:
        return json.loads(value)
    except (TypeError, json.JSONDecodeError):
        _log.debug("builder_creator_json_parse_failed", exc_info=True, extra={"op": "load_json"})
        return fallback


def keyify(value, prefix="component"):
    key = re.sub(r"[^a-z0-9]+", ".", str(value or "").lower()).strip(".")
    return key or f"{prefix}.{uuid4().hex[:8]}"


def row_api(row):
    if not row:
        return None
    result = dict(row)
    for field in JSON_FIELDS:
        if field in result:
            result[field] = load_json(result[field], [] if field in {"events", "token_dependencies", "root_structure"} else {})
    return result


def creator_payload(conn, project_id):
    definitions = [row_api(row) for row in conn.execute(
        "SELECT * FROM builder_component_definitions WHERE project_id=? ORDER BY name,id", (project_id,)
    ).fetchall()]
    usages = {row["component_definition_id"]: row["c"] for row in conn.execute(
        "SELECT component_definition_id,COUNT(*) c FROM builder_component_instances WHERE project_id=? GROUP BY component_definition_id",
        (project_id,),
    ).fetchall()}
    for item in definitions:
        item["usage_count"] = int(usages.get(item["id"], 0))
    return {
        "component_definitions": definitions,
        "component_instances": [row_api(row) for row in conn.execute(
            "SELECT * FROM builder_component_instances WHERE project_id=? ORDER BY id", (project_id,)
        ).fetchall()],
        "design_tokens": [row_api(row) for row in conn.execute(
            "SELECT * FROM builder_design_tokens WHERE project_id=? ORDER BY category,group_name,token_key", (project_id,)
        ).fetchall()],
        "project_variables": [row_api(row) for row in conn.execute(
            "SELECT * FROM builder_project_variables WHERE project_id=? ORDER BY group_name,variable_key", (project_id,)
        ).fetchall()],
        "interactions": [row_api(row) for row in conn.execute(
            "SELECT * FROM builder_interactions WHERE project_id=? ORDER BY id", (project_id,)
        ).fetchall()],
    }


def capture_creator_resources(conn, project_id):
    payload = creator_payload(conn, project_id)
    payload["component_definitions"] = [dict(row) for row in conn.execute(
        "SELECT * FROM builder_component_definitions WHERE project_id=?", (project_id,)
    ).fetchall()]
    payload["component_instances"] = [dict(row) for row in conn.execute(
        "SELECT * FROM builder_component_instances WHERE project_id=?", (project_id,)
    ).fetchall()]
    payload["design_tokens"] = [dict(row) for row in conn.execute(
        "SELECT * FROM builder_design_tokens WHERE project_id=?", (project_id,)
    ).fetchall()]
    payload["project_variables"] = [dict(row) for row in conn.execute(
        "SELECT * FROM builder_project_variables WHERE project_id=?", (project_id,)
    ).fetchall()]
    payload["interactions"] = [dict(row) for row in conn.execute(
        "SELECT * FROM builder_interactions WHERE project_id=?", (project_id,)
    ).fetchall()]
    return payload


def restore_creator_resources(conn, project_id, snapshot, document_map):
    """Restore creator resources and remap definition/document identities."""
    for table in ("builder_component_instances", "builder_component_definitions", "builder_design_tokens", "builder_project_variables", "builder_interactions"):
        conn.execute(f"DELETE FROM {table} WHERE project_id=?", (project_id,))
    definition_map = {}
    for item in snapshot.get("component_definitions") or []:
        cur = conn.execute(
            """INSERT INTO builder_component_definitions(project_id,component_key,name,description,version,root_structure,property_schema,slots,variants,default_variant,data_inputs,events,token_dependencies,metadata,created_at,updated_at)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (project_id,item["component_key"],item["name"],item.get("description",""),item.get("version",1),item.get("root_structure","[]"),item.get("property_schema","{}"),item.get("slots","{}"),item.get("variants","{}"),item.get("default_variant","default"),item.get("data_inputs","{}"),item.get("events","[]"),item.get("token_dependencies","[]"),item.get("metadata","{}"),item.get("created_at"),now()),
        )
        definition_map[int(item["id"])] = int(cur.lastrowid)
    for item in snapshot.get("component_instances") or []:
        mapped_document = document_map.get(int(item["document_id"]))
        mapped_definition = definition_map.get(int(item["component_definition_id"]))
        if mapped_document and mapped_definition:
            conn.execute("""INSERT INTO builder_component_instances(project_id,document_id,node_key,component_definition_id,variant,overrides,slot_content,bindings,responsive,created_at,updated_at)
              VALUES (?,?,?,?,?,?,?,?,?,?,?)""",(project_id,mapped_document,item["node_key"],mapped_definition,item.get("variant","default"),item.get("overrides","{}"),item.get("slot_content","{}"),item.get("bindings","{}"),item.get("responsive","{}"),item.get("created_at"),now()))
            conn.execute("UPDATE builder_nodes SET props=? WHERE document_id=? AND node_key=?",(json.dumps({"definition_id":mapped_definition,"variant":item.get("variant","default")}),mapped_document,item["node_key"]))
    for item in snapshot.get("design_tokens") or []:
        conn.execute("INSERT INTO builder_design_tokens(project_id,token_key,name,category,group_name,values_json,description,created_at,updated_at) VALUES (?,?,?,?,?,?,?,?,?)",(project_id,item["token_key"],item["name"],item["category"],item.get("group_name",""),item.get("values_json","{}"),item.get("description",""),item.get("created_at"),now()))
    for item in snapshot.get("project_variables") or []:
        conn.execute("INSERT INTO builder_project_variables(project_id,variable_key,name,value_json,value_type,group_name,created_at,updated_at) VALUES (?,?,?,?,?,?,?,?)",(project_id,item["variable_key"],item["name"],item.get("value_json","null"),item.get("value_type","string"),item.get("group_name",""),item.get("created_at"),now()))
    for item in snapshot.get("interactions") or []:
        conn.execute("INSERT INTO builder_interactions(project_id,document_id,node_key,interaction_key,trigger_type,interaction_type,configuration,created_at,updated_at) VALUES (?,?,?,?,?,?,?,?,?)",(project_id,document_map.get(item.get("document_id")),item.get("node_key"),item["interaction_key"],item["trigger_type"],item["interaction_type"],item.get("configuration","{}"),item.get("created_at"),now()))


def definition_usage(conn, project_id, definition_id):
    rows = conn.execute(
        """SELECT i.document_id,i.node_key,d.name document_name,d.document_key
           FROM builder_component_instances i JOIN builder_documents d ON d.id=i.document_id
           WHERE i.project_id=? AND i.component_definition_id=? ORDER BY d.name,i.node_key""",
        (project_id, definition_id),
    ).fetchall()
    return [dict(row) for row in rows]


def create_definition_from_subtree(conn, project_id, document_id, node_key, name, description=""):
    root = conn.execute("SELECT * FROM builder_nodes WHERE document_id=? AND node_key=?", (document_id, node_key)).fetchone()
    if not root:
        raise ValueError("Component root not found")
    subtree, frontier = [], [root]
    while frontier:
        current = frontier.pop(0)
        subtree.append(current)
        frontier.extend(conn.execute(
            "SELECT * FROM builder_nodes WHERE document_id=? AND parent_key=? ORDER BY sort_order,id",
            (document_id, current["node_key"]),
        ).fetchall())
    keys = {row["node_key"] for row in subtree}
    structure = []
    exposures = {}
    for row in subtree:
        node = {
            "key": row["node_key"], "parent_key": row["parent_key"] if row["parent_key"] in keys else None,
            "component_type": row["component_type"], "slot": row["slot"],
            "props": load_json(row["props"], {}), "styles": load_json(row["styles"], {}),
            "responsive": load_json(row["responsive"], {}), "translations": load_json(row["translations"], {}),
            "order": row["sort_order"], "visibility": row["visibility"], "metadata": load_json(row["metadata"], {}),
            "bindings": [{**dict(item), "source_config": load_json(item["source_config"], {}), "transform": load_json(item["transform"], {})} for item in conn.execute("SELECT * FROM builder_bindings WHERE project_id=? AND document_id=? AND node_key=?", (project_id, document_id, row["node_key"])).fetchall()],
            "actions": [{**dict(item), "configuration": load_json(item["configuration"], {})} for item in conn.execute("SELECT * FROM builder_actions WHERE project_id=? AND document_id=? AND node_key=?", (project_id, document_id, row["node_key"])).fetchall()],
        }
        structure.append(node)
        props = node["props"]
        if row["component_type"] == "heading" and "title" not in exposures:
            exposures["title"] = {"label": "Title", "node_key": row["node_key"], "property": "text", "type": "string", "localized": True}
        elif row["component_type"] == "image" and "image" not in exposures:
            exposures["image"] = {"label": "Image", "node_key": row["node_key"], "property": "src", "type": "image"}
        elif row["component_type"] == "button" and "button_label" not in exposures:
            exposures["button_label"] = {"label": "Button Label", "node_key": row["node_key"], "property": "label", "type": "string", "localized": True}
        elif row["component_type"] == "text" and "description" not in exposures and "body" in props:
            exposures["description"] = {"label": "Description", "node_key": row["node_key"], "property": "body", "type": "string", "localized": True}
    component_key = keyify(name)
    suffix = 2
    original = component_key
    while conn.execute("SELECT 1 FROM builder_component_definitions WHERE project_id=? AND component_key=?", (project_id, component_key)).fetchone():
        component_key = f"{original}.{suffix}"; suffix += 1
    cur = conn.execute(
        """INSERT INTO builder_component_definitions
           (project_id,component_key,name,description,root_structure,property_schema,slots,variants,default_variant,data_inputs,events,metadata,updated_at)
           VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (project_id, component_key, name, description, json.dumps(structure),
         json.dumps({"type": "object", "properties": exposures}), json.dumps({"default": {"accepts": ["*"]}}),
         json.dumps({"default": {"label": "Default", "overrides": {}}}), "default", json.dumps({}), json.dumps([]),
         json.dumps({"source": "creator", "category": "local"}), now()),
    )
    definition_id = int(cur.lastrowid)
    all_keys = [row["node_key"] for row in subtree]
    descendants = [key for key in all_keys if key != node_key]
    marks_all = ",".join("?" for _ in all_keys)
    conn.execute(f"DELETE FROM builder_bindings WHERE project_id=? AND node_key IN ({marks_all})", [project_id, *all_keys])
    conn.execute(f"DELETE FROM builder_actions WHERE project_id=? AND node_key IN ({marks_all})", [project_id, *all_keys])
    if descendants:
        marks = ",".join("?" for _ in descendants)
        conn.execute(f"DELETE FROM builder_nodes WHERE document_id=? AND node_key IN ({marks})", [document_id, *descendants])
    conn.execute(
        """UPDATE builder_nodes SET component_type='component_instance',component_reference=?,props=?,styles='{}',responsive='{}',translations='{}',metadata=?,updated_at=?
           WHERE document_id=? AND node_key=?""",
        (f"project/{component_key}", json.dumps({"definition_id": definition_id, "variant": "default"}),
         json.dumps({"display_label": name}), now(), document_id, node_key),
    )
    conn.execute(
        """INSERT INTO builder_component_instances
           (project_id,document_id,node_key,component_definition_id,variant,overrides,slot_content,bindings,responsive,updated_at)
           VALUES (?,?,?,?,?,'{}','{}','{}','{}',?)""",
        (project_id, document_id, node_key, definition_id, "default", now()),
    )
    return row_api(conn.execute("SELECT * FROM builder_component_definitions WHERE id=?", (definition_id,)).fetchone())


def insert_instance(conn, project_id, document_id, definition_id, parent_key=None, order=0, variant=None):
    definition = conn.execute("SELECT * FROM builder_component_definitions WHERE id=? AND project_id=?", (definition_id, project_id)).fetchone()
    if not definition:
        raise ValueError("Component definition not found")
    variants = load_json(definition["variants"], {})
    selected = variant or definition["default_variant"] or "default"
    if selected not in variants:
        raise ValueError("Unknown component variant")
    node_key = f"instance_{uuid4().hex[:16]}"
    conn.execute("""INSERT INTO builder_nodes(document_id,node_key,parent_key,component_type,component_reference,slot,props,styles,responsive,translations,sort_order,visibility,permissions,metadata,schema_version,updated_at)
      VALUES (?,?,?,'component_instance',?,'default',?,'{}','{}','{}',?,'visible','[]',?,4,?)""",
      (document_id,node_key,parent_key,f"project/{definition['component_key']}",json.dumps({"definition_id":definition_id,"variant":selected}),int(order),json.dumps({"display_label":definition["name"]}),now()))
    cur = conn.execute("""INSERT INTO builder_component_instances(project_id,document_id,node_key,component_definition_id,variant,overrides,slot_content,bindings,responsive,updated_at)
      VALUES (?,?,?,?,?,'{}','{}','{}','{}',?)""",(project_id,document_id,node_key,definition_id,selected,now()))
    return {"id":int(cur.lastrowid),"key":node_key,"definition_id":definition_id,"variant":selected}


def detach_instance(conn, project_id, node_key):
    instance = conn.execute("SELECT * FROM builder_component_instances WHERE project_id=? AND node_key=?",(project_id,node_key)).fetchone()
    if not instance:
        raise ValueError("Component instance not found")
    definition = conn.execute("SELECT * FROM builder_component_definitions WHERE id=?",(instance["component_definition_id"],)).fetchone()
    node = conn.execute("SELECT * FROM builder_nodes WHERE document_id=? AND node_key=?",(instance["document_id"],node_key)).fetchone()
    structure = load_json(definition["root_structure"], [])
    if not structure:
        raise ValueError("Component definition is empty")
    roots = [item for item in structure if not item.get("parent_key")]
    if len(roots) != 1:
        raise ValueError("Detach requires one component root")
    root = roots[0]
    key_map = {root["key"]: node_key}
    for item in structure:
        if item is not root:
            key_map[item["key"]] = f"{item['component_type']}_{uuid4().hex[:16]}"
    overrides = load_json(instance["overrides"], {})
    variants = load_json(definition["variants"], {})
    variant_values = (variants.get(instance["variant"]) or {}).get("overrides") or {}
    for item in structure:
        props = dict(item.get("props") or {}); styles = dict(item.get("styles") or {})
        patch = variant_values.get(item["key"], {}); props.update(patch.get("props") or {}); styles.update(patch.get("styles") or {})
        for exposed_key, value in overrides.items():
            exposure = (load_json(definition["property_schema"], {}).get("properties") or {}).get(exposed_key) or {}
            if exposure.get("node_key") == item["key"]:
                if exposure.get("property") == "visibility": item["visibility"] = "visible" if value else "hidden"
                else: props[exposure.get("property")] = value
        parent = key_map.get(item.get("parent_key"), node["parent_key"])
        values=(node["document_id"],key_map[item["key"]],parent,item["component_type"],f"core/{item['component_type']}",item.get("slot","default"),json.dumps(props),json.dumps(styles),json.dumps(item.get("responsive") or {}),json.dumps(item.get("translations") or {}),item.get("order",0),item.get("visibility","visible"),"[]",json.dumps({"detached_from":definition["component_key"]}),2,now())
        if item is root:
            conn.execute("""UPDATE builder_nodes SET parent_key=?,component_type=?,component_reference=?,slot=?,props=?,styles=?,responsive=?,translations=?,sort_order=?,visibility=?,permissions=?,metadata=?,schema_version=?,updated_at=? WHERE document_id=? AND node_key=?""",
              (parent,item["component_type"],f"core/{item['component_type']}",item.get("slot",node["slot"]),json.dumps(props),json.dumps(styles),json.dumps(item.get("responsive") or {}),json.dumps(item.get("translations") or {}),node["sort_order"],item.get("visibility","visible"),"[]",json.dumps({"detached_from":definition["component_key"]}),2,now(),node["document_id"],node_key))
        else:
            conn.execute("""INSERT INTO builder_nodes(document_id,node_key,parent_key,component_type,component_reference,slot,props,styles,responsive,translations,sort_order,visibility,permissions,metadata,schema_version,updated_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",values)
    conn.execute("DELETE FROM builder_component_instances WHERE id=?",(instance["id"],))
    return {"key":node_key,"detached":True}


def seed_official_creator_system(conn, project_id):
    tokens = [
        ("color.brand.primary", "Brand Primary", "color", {"light": "#f3cf32", "dark": "#f3cf32"}),
        ("color.background", "Background", "color", {"light": "#f7f7f4", "dark": "#111111"}),
        ("color.surface", "Surface", "color", {"light": "#ffffff", "dark": "#1d1f22"}),
        ("color.text", "Text", "color", {"light": "#15171a", "dark": "#f7f7f4"}),
        ("color.text.muted", "Muted Text", "color", {"light": "#69707d", "dark": "#aeb4bd"}),
        ("space.sm", "Small", "spacing", {"default": "8px"}), ("space.md", "Medium", "spacing", {"default": "16px"}),
        ("space.lg", "Large", "spacing", {"default": "32px"}), ("radius.card", "Card Radius", "radius", {"default": "16px"}),
        ("shadow.standard", "Standard Shadow", "shadow", {"default": "0 10px 30px rgba(20,25,35,.10)"}),
        ("duration.fast", "Fast", "duration", {"default": "160ms"}), ("duration.normal", "Normal", "duration", {"default": "260ms"}),
        ("easing.standard", "Standard", "easing", {"default": "cubic-bezier(.2,.8,.2,1)"}),
    ]
    for token_key, name, category, values in tokens:
        conn.execute(
            """INSERT OR IGNORE INTO builder_design_tokens(project_id,token_key,name,category,values_json,description,updated_at)
               VALUES (?,?,?,?,?,'Official neutral base token',?)""",
            (project_id, token_key, name, category, json.dumps(values), now()),
        )
    variables = [("brand.name", "Brand Name", "Zintriq"), ("content.maxWidth", "Content max width", "1120px"), ("layout.pagePadding", "Page padding", "24px")]
    for key, name, value in variables:
        conn.execute("INSERT OR IGNORE INTO builder_project_variables(project_id,variable_key,name,value_json,value_type,group_name,updated_at) VALUES (?,?,?,?,?,'Official',?)",
                     (project_id, key, name, json.dumps(value), "string", now()))

    workspace = conn.execute(
        """SELECT w.type FROM workspaces w
           JOIN builder_projects p ON p.workspace_id = w.id
           WHERE p.id=?""",
        (project_id,),
    ).fetchone()
    if workspace and (workspace["type"] or "") == "personal":
        return

    if not conn.execute("SELECT 1 FROM builder_component_definitions WHERE project_id=? AND component_key='official.product-card'", (project_id,)).fetchone():
        structure = [
            {"key":"product_card","parent_key":None,"component_type":"stack","slot":"default","props":{"direction":"column","gap":"12px"},"styles":{"background":"token:color.surface","padding":"token:space.md","borderRadius":"token:radius.card","boxShadow":"token:shadow.standard"},"responsive":{},"translations":{},"order":0,"visibility":"visible"},
            {"key":"product_image","parent_key":"product_card","component_type":"image","slot":"default","props":{"src":"","alt":"Product"},"styles":{"width":"100%","borderRadius":"token:radius.card"},"responsive":{},"translations":{},"order":0,"visibility":"visible"},
            {"key":"product_title","parent_key":"product_card","component_type":"heading","slot":"default","props":{"text":"Product","level":3},"styles":{"color":"token:color.text"},"responsive":{},"translations":{},"metadata":{"data_bindings":{"text":"item.name"}},"order":1,"visibility":"visible"},
            {"key":"product_description","parent_key":"product_card","component_type":"text","slot":"default","props":{"body":"Product description"},"styles":{"color":"token:color.text.muted"},"responsive":{},"translations":{},"metadata":{"data_bindings":{"body":"item.description"}},"order":2,"visibility":"visible"},
            {"key":"product_price","parent_key":"product_card","component_type":"text","slot":"default","props":{"body":"$0.00"},"styles":{"fontWeight":"700"},"responsive":{},"translations":{},"metadata":{"data_bindings":{"body":"item.price"}},"order":3,"visibility":"visible"},
            {"key":"product_button","parent_key":"product_card","component_type":"button","slot":"default","props":{"label":"View product"},"styles":{"background":"token:color.brand.primary"},"responsive":{},"translations":{},"order":4,"visibility":"visible"},
        ]
        conn.execute("""INSERT INTO builder_component_definitions(project_id,component_key,name,description,root_structure,property_schema,slots,variants,default_variant,data_inputs,events,token_dependencies,metadata,updated_at)
          VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)""", (project_id,"official.product-card","Product Card","Reusable Commerce product presentation",json.dumps(structure),
          json.dumps({"type":"object","properties":{"show_description":{"label":"Show Description","node_key":"product_description","property":"visibility","type":"boolean"},"button_label":{"label":"Button Label","node_key":"product_button","property":"label","type":"string","localized":True}}}),
          json.dumps({"actions":{"accepts":["button"]}}),json.dumps({"default":{"label":"Default","overrides":{}},"compact":{"label":"Compact","overrides":{"product_card":{"styles":{"gap":"8px","padding":"token:space.sm"}},"product_description":{"visibility":"hidden"}}}}),"default",
          json.dumps({"product":{"type":"object","compatible":"Commerce.Product"}}),json.dumps(["onOpen","onAddToCart"]),json.dumps(["color.surface","color.text","color.brand.primary","radius.card","shadow.standard"]),json.dumps({"category":"official","package_ready":True}),now()))

    product_definition = conn.execute("SELECT id FROM builder_component_definitions WHERE project_id=? AND component_key='official.product-card'", (project_id,)).fetchone()
    customer = conn.execute("SELECT id FROM builder_documents WHERE project_id=? AND document_key='customer-site'", (project_id,)).fetchone()
    if product_definition and customer and not conn.execute("SELECT 1 FROM builder_nodes WHERE document_id=? AND node_key='official_product_repeater'", (customer["id"],)).fetchone():
        root = conn.execute("SELECT node_key FROM builder_nodes WHERE document_id=? AND parent_key IS NULL ORDER BY id LIMIT 1", (customer["id"],)).fetchone()
        conn.execute("""INSERT INTO builder_nodes(document_id,node_key,parent_key,component_type,component_reference,slot,props,styles,responsive,translations,sort_order,visibility,permissions,metadata,schema_version,updated_at)
          VALUES (?,'official_product_repeater',?,'repeater','core/repeater','default',?,?,'{}','{}',4,'visible','[]',?,4,?)""",
          (customer["id"],root["node_key"] if root else None,json.dumps({"empty_text":"No products yet"}),json.dumps({"padding":"token:space.lg","display":"grid","gridTemplateColumns":"repeat(auto-fit,minmax(220px,1fr))","gap":"token:space.md"}),json.dumps({"display_label":"Products"}),now()))
        conn.execute("""INSERT OR IGNORE INTO builder_bindings(project_id,document_id,node_key,binding_key,source_type,source_config,transform,updated_at)
          VALUES (?,?, 'official_product_repeater','items','domain',?,'{}',?)""",(project_id,customer["id"],json.dumps({"source_id":"commerce.products","query":{"limit":8}}),now()))
        insert_instance(conn,project_id,customer["id"],product_definition["id"],"official_product_repeater",0,"default")

    if not conn.execute("SELECT 1 FROM builder_component_definitions WHERE project_id=? AND component_key='official.customer-navigation'", (project_id,)).fetchone():
        nav_structure=[{"key":"customer_navigation","parent_key":None,"component_type":"navigation","slot":"default","props":{"brand":"Zintriq","links":"Home|/home\nPlaces|/venues\nAccount|account"},"styles":{"background":"token:color.surface","color":"token:color.text","padding":"token:space.md"},"responsive":{"mobile":{"padding":"token:space.sm"}},"translations":{},"order":0,"visibility":"visible"}]
        nav_properties={"type":"object","properties":{"brand":{"label":"Brand","node_key":"customer_navigation","property":"brand","type":"string","localized":True},"links":{"label":"Navigation Links","node_key":"customer_navigation","property":"links","type":"string","localized":True}}}
        nav_slots={"logo":{"accepts":["image"]},"actions":{"accepts":["button"]}}
        nav_variants={"light":{"label":"Light","overrides":{}},"transparent":{"label":"Transparent","overrides":{"customer_navigation":{"styles":{"background":"transparent"}}}}}
        conn.execute("""INSERT INTO builder_component_definitions(project_id,component_key,name,description,root_structure,property_schema,slots,variants,default_variant,data_inputs,events,token_dependencies,metadata,updated_at)
          VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",(project_id,"official.customer-navigation","Customer Navigation","Shared responsive navigation for Customer pages",json.dumps(nav_structure),json.dumps(nav_properties),json.dumps(nav_slots),json.dumps(nav_variants),"light",json.dumps({}),json.dumps(["onNavigate"]),json.dumps(["color.surface","color.text","space.md"]),json.dumps({"category":"official","section":"navigation","mobile_menu":True}),now()))
    nav_definition=conn.execute("SELECT * FROM builder_component_definitions WHERE project_id=? AND component_key='official.customer-navigation'",(project_id,)).fetchone()
    home_nav=conn.execute("SELECT * FROM builder_nodes WHERE document_id=(SELECT id FROM builder_documents WHERE project_id=? AND document_key='customer-site') AND node_key='official_customer_nav'",(project_id,)).fetchone()
    if nav_definition and home_nav and home_nav["component_type"]=="component_instance":
        conn.execute("DELETE FROM builder_component_instances WHERE project_id=? AND document_id=? AND node_key=?",(project_id,home_nav["document_id"],home_nav["node_key"]))
        conn.execute("UPDATE builder_nodes SET component_type='navigation',component_reference='core/navigation',props=?,styles=?,responsive='{}',translations='{}',metadata='{}',schema_version=2,updated_at=? WHERE id=?",(json.dumps({"brand":"Zintriq","links":"Home|/home\nPlaces|/venues\nAccount|account"}),json.dumps({"padding":"18px 24px","background":"#ffffff"}),now(),home_nav["id"]))
    storefront=conn.execute("SELECT id FROM builder_documents WHERE project_id=? AND document_key='storefront'",(project_id,)).fetchone()
    if nav_definition and storefront and not conn.execute("SELECT 1 FROM builder_component_instances WHERE project_id=? AND document_id=? AND component_definition_id=?",(project_id,storefront["id"],nav_definition["id"])).fetchone():
        insert_instance(conn,project_id,storefront["id"],nav_definition["id"],None,0,"light")
    qr_runtime=conn.execute("SELECT id FROM builder_documents WHERE project_id=? AND document_key='qr-runtime'",(project_id,)).fetchone()
    if nav_definition and qr_runtime and not conn.execute("SELECT 1 FROM builder_component_instances WHERE project_id=? AND document_id=? AND component_definition_id=?",(project_id,qr_runtime["id"],nav_definition["id"])).fetchone():
        insert_instance(conn,project_id,qr_runtime["id"],nav_definition["id"],None,0,"light")

    business=conn.execute("SELECT id FROM builder_documents WHERE project_id=? AND document_key='business-site'",(project_id,)).fetchone()
    business_root=conn.execute("SELECT * FROM builder_nodes WHERE document_id=? AND node_key='official_business_shell'",(business["id"],)).fetchone() if business else None
    if business_root and business_root["component_type"]=="app_shell" and not conn.execute("SELECT 1 FROM builder_component_definitions WHERE project_id=? AND component_key='official.business-app-shell'",(project_id,)).fetchone():
        definition=create_definition_from_subtree(conn,project_id,business["id"],business_root["node_key"],"Business App Shell","Reusable operational shell with controlled App Module slot")
        conn.execute("UPDATE builder_component_definitions SET component_key='official.business-app-shell',slots=?,token_dependencies=?,metadata=?,updated_at=? WHERE id=?",(json.dumps({"sidebar":{"accepts":["navigation"]},"header":{"accepts":["header","button","text"]},"content":{"accepts":["app_module","section"]}}),json.dumps(["color.brand.primary","color.background","color.surface","color.text"]),json.dumps({"category":"official","application_shell":True,"controlled_modules":True}),now(),definition["id"]))
        conn.execute("UPDATE builder_nodes SET component_reference='project/official.business-app-shell' WHERE document_id=? AND node_key=?",(business["id"],business_root["node_key"]))


def validate_creator_resources(snapshot):
    issues = []
    definitions = {int(item["id"]): item for item in snapshot.get("component_definitions", [])}
    for instance in snapshot.get("component_instances", []):
        if int(instance.get("component_definition_id") or 0) not in definitions:
            issues.append({"level": "error", "message": f"Component instance {instance.get('node_key')} has a missing definition"})
    tokens = {item.get("token_key") for item in snapshot.get("design_tokens", [])}
    for definition in definitions.values():
        for dependency in load_json(definition.get("token_dependencies"), []):
            if dependency not in tokens:
                issues.append({"level": "warning", "message": f"{definition.get('name')} references missing token {dependency}"})
    return issues
