"""Published-snapshot runtime for Universal Builder native documents."""

from __future__ import annotations

import html
import json
import logging
import re

_log = logging.getLogger("app.universal_builder")


def rewrite_account_href(href: str, work=None) -> str:
    from work_urls import rewrite_account_href as _rewrite

    return _rewrite(href, work)


STYLE_KEYS = {
    "display": "display", "color": "color", "background": "background",
    "padding": "padding", "margin": "margin", "gap": "gap", "fontSize": "font-size",
    "fontWeight": "font-weight", "textAlign": "text-align", "borderRadius": "border-radius",
    "minHeight": "min-height", "height": "height", "maxWidth": "max-width", "minWidth": "min-width",
    "flexDirection": "flex-direction", "alignItems": "align-items", "justifyContent": "justify-content",
    "flexWrap": "flex-wrap", "gridTemplateColumns": "grid-template-columns", "position": "position",
    "top": "top", "right": "right", "bottom": "bottom", "left": "left", "boxShadow": "box-shadow",
    "border": "border", "opacity": "opacity", "overflow": "overflow",
    "transform": "transform", "filter": "filter",
}


def _json(value, fallback):
    if isinstance(value, (dict, list)):
        return value
    try:
        return json.loads(value or "")
    except (TypeError, json.JSONDecodeError):
        _log.debug("builder_runtime_json_parse_failed", exc_info=True, extra={"op": "json"})
        return fallback


def evaluate_condition(expression, context) -> bool:
    if not expression:
        return True
    if "and" in expression:
        return all(evaluate_condition(item, context) for item in expression["and"])
    if "or" in expression:
        return any(evaluate_condition(item, context) for item in expression["or"])
    if "not" in expression:
        return not evaluate_condition(expression["not"], context)
    left = _path(context, expression.get("left"))
    right = expression.get("right")
    operation = expression.get("operator", "eq")
    return {
        "eq": left == right, "ne": left != right,
        "contains": right in left if isinstance(left, (str, list, dict)) else False,
        "gt": left > right if left is not None and right is not None else False,
        "gte": left >= right if left is not None and right is not None else False,
        "lt": left < right if left is not None and right is not None else False,
        "lte": left <= right if left is not None and right is not None else False,
        "truthy": bool(left), "falsy": not bool(left),
    }.get(operation, False)


def _path(value, path):
    if not path:
        return value
    current = value
    for part in str(path).split("."):
        if not isinstance(current, dict):
            return None
        current = current.get(part)
    return current


def _css_name(value):
    return re.sub(r"[^a-z0-9-]", "-", str(value).lower().replace(".", "-"))


def _safe_style(styles):
    declarations = []
    for key, value in (_json(styles, {}) or {}).items():
        if str(key).lower().startswith("on"):
            continue
        if key in STYLE_KEYS and isinstance(value, (str, int, float)) and ";" not in str(value):
            rendered = str(value)
            if rendered.startswith("token:"):
                rendered = f"var(--ub-token-{_css_name(rendered[6:])})"
            elif rendered.startswith("variable:"):
                rendered = f"var(--ub-var-{_css_name(rendered[9:])})"
            declarations.append(f"{STYLE_KEYS[key]}:{rendered}")
    return ";".join(declarations)


def _safe_href(value):
    value = str(value or "#")
    parsed = urlparse(value)
    return value if not parsed.scheme or parsed.scheme in {"http", "https", "mailto", "tel"} else "#"


def _bindings(snapshot, document_id):
    return [item for item in snapshot.get("bindings", []) if not item.get("document_id") or item.get("document_id") == document_id]


def _bound_value(binding, context):
    config = _json(binding.get("source_config"), {})
    source_type = binding.get("source_type")
    if source_type == "literal":
        return config.get("value")
    if source_type in {"project", "state", "record", "item", "variable"}:
        return _path(context.get(source_type, {}), config.get("path") or config.get("key"))
    if source_type == "collection":
        return context.get("collections", {}).get(config.get("model_key"), [])
    if source_type == "domain":
        return context.get("domain", {}).get(config.get("source_id"), [])
    return None


def render_document(snapshot: dict, document_key: str, *, state=None, notice: str = "", csrf: str = "", locale: str = "en",
                    domain_data=None, route_path: str = "", work=None, invoke_url: str = "",
                    collections=None) -> str | None:
    documents = snapshot.get("documents") or []
    document = next((item for item in documents if item.get("key", item.get("document_key")) == document_key), None)
    if not document:
        return None
    document_id = document.get("id")
    if collections is None:
        collections = {}
        for record in snapshot.get("data_records") or []:
            collections.setdefault(record.get("model_key"), []).append(_json(record.get("data"), {}))
    variables = {item.get("variable_key"): _json(item.get("value_json"), None) for item in snapshot.get("project_variables", [])}
    context = {"project": snapshot.get("project") or {}, "state": state or {}, "variable": variables, "collections": collections, "domain": domain_data or {}}
    conditions = {item.get("id"): _json(item.get("expression"), {}) for item in snapshot.get("conditions", [])}
    bindings = _bindings(snapshot, document_id)
    actions_by_node: dict[str, list] = {}
    for item in snapshot.get("actions", []):
        if item.get("document_id") not in (None, document_id):
            continue
        if _json(item.get("configuration"), {}).get("enabled") is False:
            continue
        actions_by_node.setdefault(item.get("node_key"), []).append(item)
    from builder_kernel.registry import kernel
    kernel.ensure_core()
    project_slug = (snapshot.get("project") or {}).get("slug") or "project"
    runtime_invoke = invoke_url or f"/build/{project_slug}/{document_key}/runtime/invoke"
    definitions = {int(item.get("id")): item for item in snapshot.get("component_definitions", [])}
    instances = {item.get("node_key"): item for item in snapshot.get("component_instances", []) if item.get("document_id") == document_id}
    interactions = {}
    for item in snapshot.get("interactions", []):
        if item.get("document_id") not in (None, document_id):
            continue
        if _json(item.get("configuration"), {}).get("enabled") is False:
            continue
        interactions.setdefault(item.get("node_key"), []).append(item)
    raw_nodes = [item for item in snapshot.get("nodes", []) if item.get("document_id") == document_id]
    children = {}
    for item in raw_nodes:
        children.setdefault(item.get("parent_key"), []).append(item)
    for group in children.values():
        group.sort(key=lambda item: (item.get("sort_order", 0), item.get("id", 0)))

    def render_node(node, local_context=None, child_map=None):
        local_children = child_map or children
        node_context = dict(context)
        if local_context:
            node_context.update(local_context)
        if node.get("visibility") == "hidden":
            return ""
        if node.get("condition_id") and not evaluate_condition(conditions.get(node["condition_id"]), node_context):
            return ""
        props = _json(node.get("props"), {})
        localized = (_json(node.get("translations"), {}) or {}).get(locale) or {}
        for binding in bindings:
            if binding.get("node_key") == node.get("node_key"):
                value = _bound_value(binding, node_context)
                if value is not None:
                    props[binding.get("binding_key")] = value
        for binding in node.get("bindings") or []:
            value = _bound_value(binding, node_context)
            if value is not None: props[binding.get("binding_key")] = value
        if isinstance(localized, dict):
            props.update(localized)
        component = node.get("component_type", "text")
        style = html.escape(_safe_style(node.get("styles")), quote=True)
        motion_names = " ".join(str(item.get("interaction_type") or "fade") for item in interactions.get(node.get("node_key"), []))
        attrs = f' data-node="{html.escape(str(node.get("node_key")), quote=True)}" data-motion="{html.escape(motion_names, quote=True)}" style="{style}"'
        rendered_children = "".join(render_node(child, local_context, local_children) for child in local_children.get(node.get("node_key"), []))
        if component == "component_instance":
            instance = instances.get(node.get("node_key"))
            definition = definitions.get(int((instance or {}).get("component_definition_id") or props.get("definition_id") or 0))
            if not instance or not definition:
                return f"<div class='ub-component-error'{attrs}>Reusable component is unavailable</div>"
            structure = _json(definition.get("root_structure"), [])
            variant = (_json(definition.get("variants"), {}) or {}).get(instance.get("variant")) or {}
            variant_overrides = variant.get("overrides") or {}
            instance_overrides = _json(instance.get("overrides"), {})
            exposures = ((_json(definition.get("property_schema"), {}) or {}).get("properties") or {})
            virtual = []
            for original in structure:
                item = dict(original); item["node_key"] = item.get("key")
                item["props"] = dict(item.get("props") or {}); item["styles"] = dict(item.get("styles") or {})
                patch = variant_overrides.get(item["node_key"], {})
                item["props"].update(patch.get("props") or {}); item["styles"].update(patch.get("styles") or {})
                if "visibility" in patch: item["visibility"] = patch["visibility"]
                for exposed_key, value in instance_overrides.items():
                    exposure = exposures.get(exposed_key) or {}
                    if exposure.get("node_key") == item["node_key"]:
                        if exposure.get("property") == "visibility": item["visibility"] = "visible" if value else "hidden"
                        else: item["props"][exposure.get("property")] = value
                for property_key, path in ((item.get("metadata") or {}).get("data_bindings") or {}).items():
                    bound = _path(node_context, path)
                    if bound is not None: item["props"][property_key] = bound
                virtual.append(item)
            virtual_children = {}
            for item in virtual: virtual_children.setdefault(item.get("parent_key"), []).append(item)
            for group in virtual_children.values(): group.sort(key=lambda value: value.get("order", 0))
            content = "".join(render_node(item, local_context, virtual_children) for item in virtual_children.get(None, []))
            return f"<div class='ub-component-instance' data-component='{html.escape(str(definition.get('component_key')), quote=True)}'{attrs}>{content}{rendered_children}</div>"
        if component == "section":
            return f"<section class='ub-section'{attrs}>{rendered_children}</section>"
        if component == "stack":
            layout = f"{style};display:flex;flex-direction:{html.escape(str(props.get('direction') or 'column'), quote=True)};gap:{html.escape(str(props.get('gap') or '16px'), quote=True)};align-items:{html.escape(str(props.get('align') or 'stretch'), quote=True)};justify-content:{html.escape(str(props.get('distribution') or 'start'), quote=True)};flex-wrap:{'wrap' if props.get('wrap') else 'nowrap'}"
            return f"<div class='ub-stack' data-node='{html.escape(str(node.get('node_key')), quote=True)}' data-motion='{html.escape(motion_names, quote=True)}' style='{layout}'>{rendered_children}</div>"
        if component == "grid":
            columns = max(1, min(12, int(props.get("columns") or 3)))
            template = f"repeat(auto-fit,minmax({props.get('min_column_width') or '220px'},1fr))" if props.get("auto_fit", True) else f"repeat({columns},minmax(0,1fr))"
            return f"<div class='ub-grid' data-node='{html.escape(str(node.get('node_key')), quote=True)}' data-motion='{html.escape(motion_names, quote=True)}' style='{style};display:grid;grid-template-columns:{html.escape(template, quote=True)};gap:{html.escape(str(props.get('gap') or '16px'), quote=True)}'>{rendered_children}</div>"
        if component == "overlay":
            return f"<div class='ub-overlay' data-node='{html.escape(str(node.get('node_key')), quote=True)}' data-motion='{html.escape(motion_names, quote=True)}' style='{style};position:relative;min-height:{html.escape(str(props.get('min_height') or '320px'), quote=True)}'>{rendered_children}</div>"
        if component == "navigation":
            links = []
            for line in str(props.get("links") or "").splitlines():
                label, separator, target = line.partition("|")
                if label.strip() and separator:
                    links.append(f"<a href='{html.escape(_safe_href(rewrite_account_href(target.strip(), work)), quote=True)}'>{html.escape(label.strip())}</a>")
            return f"<nav class='ub-navigation'{attrs}><a class='ub-navigation__brand' href='/app/builder'>{html.escape(str(props.get('brand') or 'Zintriq'))}</a><div>{''.join(links)}</div>{rendered_children}</nav>"
        if component == "hero":
            image = f"<img src='{html.escape(_safe_href(props.get('image')), quote=True)}' alt=''>" if props.get("image") else ""
            return f"<section class='ub-hero'{attrs}><div><span>{html.escape(str(props.get('eyebrow') or ''))}</span><h1>{html.escape(str(props.get('title') or ''))}</h1><p>{html.escape(str(props.get('body') or ''))}</p>{rendered_children}</div>{image}</section>"
        if component in {"heading", "header"}:
            level = max(1, min(6, int(props.get("level", 1 if component == "header" else 2))))
            text = props.get("text") or props.get("title") or ""
            subtitle = f"<p>{html.escape(str(props.get('subtitle')))}</p>" if props.get("subtitle") else ""
            return f"<div{attrs}><h{level}>{html.escape(str(text))}</h{level}>{subtitle}{rendered_children}</div>"
        if component in {"text", "info"}:
            body = props.get("body") or props.get("text") or ""
            title = f"<h3>{html.escape(str(props.get('title')))}</h3>" if props.get("title") else ""
            return f"<div{attrs}>{title}<p>{html.escape(str(body))}</p>{rendered_children}</div>"
        if component == "image":
            return f"<img{attrs} src='{html.escape(str(props.get('src','')), quote=True)}' alt='{html.escape(str(props.get('alt','')), quote=True)}'>"
        if component == "button":
            node_actions = actions_by_node.get(node.get("node_key")) or list(node.get("actions") or [])
            invokeable = []
            navigable = []
            for item in node_actions:
                action_id = kernel.resolve_action_id(item.get("action_type") or item.get("type"))
                if action_id in {"core/open_page", "core/external_link", "core/navigate_to_page"}:
                    navigable.append(item)
                elif action_id:
                    invokeable.append(item)
            label = html.escape(str(props.get("label", "Continue")))
            if invokeable:
                chosen = invokeable[0]
                action_key = html.escape(str(chosen.get("action_key") or chosen.get("key") or ""), quote=True)
                return (
                    f"<button type='button' class='ub-button'{attrs} data-action-key='{action_key}' "
                    f"data-invoke='{html.escape(runtime_invoke, quote=True)}'>{label}</button>"
                )
            if navigable:
                action = navigable[0]
                config = _json(action.get("configuration"), {})
                href = config.get("url") or config.get("path") or config.get("target") or "#"
                return f"<a class='ub-button' href='{html.escape(_safe_href(href), quote=True)}'{attrs}>{label}</a>"
            return f"<button type='button' class='ub-button'{attrs}>{label}</button>"
        if component == "repeater":
            items = props.get("items") or []
            if not isinstance(items, list):
                items = []
            sort_field = props.get("sort_field")
            if sort_field and items:
                reverse = props.get("sort_direction") == "desc"
                items = sorted(items, key=lambda item: (item.get(sort_field, "") if isinstance(item, dict) else ""), reverse=reverse)
            try: limit = max(1, min(200, int(props.get("limit")))) if props.get("limit") else None
            except (TypeError, ValueError): limit = None
            if limit:
                items = items[:limit]
            if not items:
                return f"<p{attrs}>{html.escape(str(props.get('empty_text','No items yet')))}</p>"
            item_nodes = local_children.get(node.get("node_key"), [])
            return f"<div class='ub-grid'{attrs}>" + "".join(
                "<article class='ub-card'>" + (
                    "".join(render_node(child, {"item": item, "record": item}, local_children) for child in item_nodes)
                    if item_nodes else
                    "".join(f"<p><strong>{html.escape(str(k))}</strong>: {html.escape(str(v))}</p>" for k, v in item.items())
                ) + "</article>"
                for item in items if isinstance(item, dict)
            ) + "</div>"
        if component == "store_grid":
            items = props.get("items") or []
            if not isinstance(items, list):
                items = []
            try: columns = max(1, min(4, int(props.get("columns") or 3)))
            except (TypeError, ValueError): columns = 3
            try: limit = max(1, min(24, int(props.get("limit") or 6)))
            except (TypeError, ValueError): limit = 6
            cards = []
            for item in items[:limit]:
                if not isinstance(item, dict): continue
                image_url = item.get("logo_url") or item.get("background_image") or ""
                image_html = f"<img src='{html.escape(_safe_href(image_url), quote=True)}' alt=''>" if image_url else "<span class='ub-store-card__mark'>●</span>"
                description = f"<p>{html.escape(str(item.get('description') or ''))}</p>" if props.get("show_description", True) else ""
                cards.append(f"<a class='ub-store-card' href='/store/{html.escape(str(item.get('slug') or ''), quote=True)}'>{image_html}<div><h3>{html.escape(str(item.get('name') or 'Store'))}</h3>{description}<small>{html.escape(str(item.get('address') or ''))}</small></div></a>")
            content = "".join(cards) or f"<p>{html.escape(str(props.get('empty_text') or 'No stores yet'))}</p>"
            return f"<section class='ub-domain-section'{attrs}><h2>{html.escape(str(props.get('title') or 'Stores'))}</h2><div class='ub-store-grid' style='--columns:{columns}'>{content}</div></section>"
        if component == "app_shell":
            node_children = local_children.get(node.get("node_key"), [])
            sidebar = "".join(render_node(child, local_context, local_children) for child in node_children if child.get("slot") == "sidebar")
            header = "".join(render_node(child, local_context, local_children) for child in node_children if child.get("slot") == "header")
            content = "".join(render_node(child, local_context, local_children) for child in node_children if child.get("slot") not in {"sidebar", "header"})
            return f"<div class='ub-app-shell'{attrs} data-accent='{html.escape(str(props.get('accent') or '#f3cf32'), quote=True)}'><aside>{sidebar}</aside><div class='ub-app-shell__main'><header>{header}</header><div class='ub-app-shell__content'>{content}</div></div></div>"
        if component == "app_module":
            from universal_builder_modules import app_module_payload
            module_id = str(props.get("module_id") or "")
            module = app_module_payload(module_id)
            if not module:
                return f"<div class='ub-module-error'{attrs}>Unavailable App Module</div>"
            project_id = context.get("project", {}).get("id") or ""
            try: height = max(320, min(1200, int(props.get("height") or 720)))
            except (TypeError, ValueError): height = 720
            src = f"/app/builder-module/{html.escape(module_id, quote=True)}?project_id={html.escape(str(project_id), quote=True)}"
            return f"<section class='ub-app-module'{attrs}><div class='ub-app-module__bar'><span>App Module</span><strong>{html.escape(str(props.get('title') or module['name']))}</strong><a href='{html.escape(module['manager_url'], quote=True)}'>Open manager</a></div><iframe src='{src}' title='{html.escape(module['name'], quote=True)}' style='height:{height}px' loading='lazy'></iframe></section>"
        if component == "form":
            project_slug = context.get("project", {}).get("slug") or "project"
            target_model = html.escape(str(props.get("target_model") or ""), quote=True)
            form_nodes = local_children.get(node.get("node_key"), [])
            field_html = []
            for child in form_nodes:
                if child.get("component_type") == "form_field":
                    cp = _json(child.get("props"), {})
                    fname = html.escape(str(cp.get("field_name") or "field"), quote=True)
                    flabel = html.escape(str(cp.get("label") or "Field"))
                    ftype = str(cp.get("field_type") or "text")
                    fplaceholder = html.escape(str(cp.get("placeholder") or ""), quote=True)
                    freq = " required" if cp.get("required") else ""
                    fhelp = f"<small>{html.escape(str(cp.get('help_text') or ''))}</small>" if cp.get("help_text") else ""
                    input_map = {
                        "text": f"<input type='text' name='{fname}' placeholder='{fplaceholder}'{freq}>",
                        "email": f"<input type='email' name='{fname}' placeholder='{fplaceholder}'{freq}>",
                        "number": f"<input type='number' name='{fname}' placeholder='{fplaceholder}'{freq}>",
                        "date": f"<input type='date' name='{fname}'{freq}>",
                        "textarea": f"<textarea name='{fname}' placeholder='{fplaceholder}'{freq}></textarea>",
                        "checkbox": f"<label class='ub-form-checkbox'><input type='checkbox' name='{fname}' value='true'> {flabel}</label>",
                        "select": f"<select name='{fname}'{freq}><option value=''>—</option></select>",
                    }
                    if ftype == "checkbox":
                        field_html.append(f"<div class='ub-form-field'>{input_map.get(ftype, input_map['text'])}{fhelp}</div>")
                    else:
                        field_html.append(f"<div class='ub-form-field'><label>{flabel}{input_map.get(ftype, input_map['text'])}</label>{fhelp}</div>")
            fields_content = "".join(field_html) or "<p>No form fields configured.</p>"
            submit_action = None
            for item in actions_by_node.get(node.get("node_key")) or []:
                event_type = str(item.get("event_type") or "")
                if event_type in {"on_submit", "submit"}:
                    submit_action = item
                    break
            action_key = html.escape(str((submit_action or {}).get("action_key") or ""), quote=True)
            invoke_attr = html.escape(runtime_invoke, quote=True)
            from builder_kernel.limits import HONEYPOT_FIELD

            hp = html.escape(HONEYPOT_FIELD, quote=True)
            return f"""<form class='ub-form' method='post' action='{invoke_attr}'{attrs} data-target-model='{target_model}' data-action-key='{action_key}' data-invoke='{invoke_attr}'>
              <input type='hidden' name='csrf_token' value='{html.escape(csrf, quote=True)}'>
              <div aria-hidden='true' style='position:absolute;left:-10000px;top:auto;width:1px;height:1px;overflow:hidden'>
                <label>Leave blank<input type='text' name='{hp}' tabindex='-1' autocomplete='off'></label>
              </div>
              <h2>{html.escape(str(props.get('title','Submit')))}</h2>
              {fields_content}
              <button class='ub-button' type='submit'>{html.escape(str(props.get('submit_label','Submit')))}</button>
              <div class='ub-form-messages'><p class='ub-form-success' hidden>{html.escape(str(props.get('success_message','Submitted successfully')))}</p><p class='ub-form-failure' hidden>{html.escape(str(props.get('failure_message','Something went wrong. Please try again.')))}</p></div>
              </form>"""
        if component == "booking":
            project_slug = context.get("project", {}).get("slug") or "project"
            return f"""<form class='ub-form' method='post' action='/builder-runtime/{html.escape(str(project_slug), quote=True)}/{html.escape(str(document_key), quote=True)}/booking'{attrs}>
              <h2>{html.escape(str(props.get('title','Book your visit')))}</h2>
              <input type='hidden' name='csrf_token' value='{html.escape(csrf, quote=True)}'>
              <label>Name<input required name='customer_name'></label>
              <label>Email<input required type='email' name='customer_email'></label>
              <label>Date and time<input required type='datetime-local' name='starts_at'></label>
              <label>Notes<textarea name='notes'></textarea></label>
              <button class='ub-button' type='submit'>Request booking</button></form>"""
        if component == "survey":
            return f"<section class='ub-capability-card'{attrs}><span>Feedback capability</span><h2>{html.escape(str(props.get('title') or 'Your feedback'))}</h2><p>{html.escape(str(props.get('body') or ''))}</p><a class='ub-button' href='{html.escape(rewrite_account_href('/account', work), quote=True)}'>Share feedback</a></section>"
        return f"<div{attrs}>{rendered_children}</div>"

    body = "".join(render_node(node) for node in children.get(None, []) + children.get("", []))
    document_schema = _json(document.get("schema"), {})
    metadata = document_schema.get("metadata") or {}
    title = html.escape(str(metadata.get("title") or document.get("name") or snapshot.get("project", {}).get("name") or "Project"))
    description = html.escape(str(metadata.get("description") or ""), quote=True)
    notice_html = f"<div class='ub-notice'>{html.escape(notice)}</div>" if notice else ""
    direction = "rtl" if str(locale).lower().startswith("ar") else "ltr"
    token_css = []
    for token in snapshot.get("design_tokens", []):
        values = _json(token.get("values_json"), {}); value = values.get("light", values.get("default", ""))
        if isinstance(value, (str, int, float)) and ";" not in str(value): token_css.append(f"--ub-token-{_css_name(token.get('token_key'))}:{value}")
    for variable in snapshot.get("project_variables", []):
        value = _json(variable.get("value_json"), "")
        if isinstance(value, (str, int, float)) and ";" not in str(value): token_css.append(f"--ub-var-{_css_name(variable.get('variable_key'))}:{value}")
    state_css=[]
    pseudo={"hover":":hover","press":":active","focus":":focus-visible","selected":"[aria-selected='true']"}
    for interaction in snapshot.get("interactions", []):
        if interaction.get("document_id") not in (None, document_id) or interaction.get("trigger_type") not in pseudo: continue
        config=_json(interaction.get("configuration"),{})
        if config.get("enabled") is False:
            continue
        declarations=_safe_style(config.get("styles") or {})
        if declarations:
            selector=f"[data-node='{str(interaction.get('node_key')).replace(chr(39),'')}']{pseudo[interaction['trigger_type']]}"
            state_css.append(f"{selector}{{{declarations}}}")
    creator_css = f":root{{{';'.join(token_css)}}}{''.join(state_css)}[data-motion~='fade']{{animation:ub-fade var(--ub-token-duration-normal,260ms) ease both}}[data-motion~='slide-up']{{animation:ub-slide-up var(--ub-token-duration-normal,260ms) ease both}}[data-motion~='scale']:hover{{transform:scale(1.025)}}[data-motion~='press']:active{{transform:scale(.98)}}@keyframes ub-fade{{from{{opacity:0}}}}@keyframes ub-slide-up{{from{{opacity:0;transform:translateY(20px)}}}}@media(prefers-reduced-motion:reduce){{[data-motion]{{animation:none!important;transition:none!important;transform:none!important}}}}"
    return f"""<!doctype html><html lang='{html.escape(locale, quote=True)}' dir='{direction}'><head><meta charset='utf-8'><meta name='viewport' content='width=device-width,initial-scale=1'>
    <title>{title}</title><meta name='description' content='{description}'>
    <meta name='csrf-token' content='{html.escape(csrf, quote=True)}'>
    <meta name='ub-invoke' content='{html.escape(runtime_invoke, quote=True)}'>
    <meta name='ub-document-key' content='{html.escape(str(document_key), quote=True)}'>
    <link rel='stylesheet' href='/static/builder/universal-runtime.css'><style>{creator_css}</style></head>
    <body lang='{html.escape(locale, quote=True)}'><main class='ub-page'>{notice_html}{body}</main>
    <script src='/static/builder/published-runtime.js'></script></body></html>"""


def published_snapshot(conn, project_slug: str):
    row = conn.execute(
        """SELECT r.snapshot, p.* FROM builder_projects p
           JOIN builder_deployments d ON d.project_id=p.id AND d.environment='production' AND d.channel='web'
           JOIN builder_project_revisions r ON r.id=d.revision_id
           WHERE p.slug=? AND d.status='active'""", (project_slug,),
    ).fetchone()
    return (row, _json(row["snapshot"], {})) if row else (None, None)


def render_record_detail(
    *,
    project_slug: str,
    model_key: str,
    record: dict,
    model_name: str = "",
) -> str:
    """Read-only detail page. All user values are html.escaped."""
    data = record.get("data") if isinstance(record.get("data"), dict) else {}
    rows = "".join(
        f"<tr><th scope='row'>{html.escape(str(key))}</th><td>{html.escape(str(value))}</td></tr>"
        for key, value in data.items()
    ) or "<tr><td colspan='2'>No fields</td></tr>"
    title = html.escape(str(model_name or model_key))
    record_key = html.escape(str(record.get("record_key") or ""))
    slug = html.escape(str(project_slug))
    return f"""<!doctype html><html><head><meta charset='utf-8'><title>{title}</title>
<meta name='robots' content='noindex'>
<style>body{{font-family:system-ui,sans-serif;margin:2rem;color:#111}}
table{{border-collapse:collapse;width:min(40rem,100%)}}th,td{{border:1px solid #ddd;padding:.5rem;text-align:left}}
th{{width:30%;background:#f6f6f6}}a{{color:#0645ad}}</style></head>
<body><p><a href='/build/{slug}'>Back</a></p>
<h1>{title}</h1><p><code>{record_key}</code></p>
<table><tbody>{rows}</tbody></table></body></html>"""
