from __future__ import annotations

import hashlib
from typing import Any

from playwright.sync_api import Page

from eliapplybot.models import DetectedField

SCAN_SCRIPT = r"""
() => {
  const fields = [];
  const seenGroups = new Set();

  const norm = (value) => (value || "").replace(/\s+/g, " ").trim();
  const visible = (el) => {
    if (!el || el.hidden) return false;
    const style = window.getComputedStyle(el);
    if (style.display === "none" || style.visibility === "hidden") return false;
    const rect = el.getBoundingClientRect();
    return rect.width > 0 && rect.height > 0;
  };
  const esc = (value) => {
    if (window.CSS && CSS.escape) return CSS.escape(value);
    return String(value).replace(/["\\]/g, "\\$&");
  };
  const cssPath = (el) => {
    if (el.id) return `#${esc(el.id)}`;
    const parts = [];
    let current = el;
    while (current && current.nodeType === Node.ELEMENT_NODE && parts.length < 5) {
      let part = current.nodeName.toLowerCase();
      if (current.name && ["input", "select", "textarea", "button"].includes(part)) {
        part += `[name="${esc(current.name)}"]`;
        parts.unshift(part);
        break;
      }
      const parent = current.parentElement;
      if (parent) {
        const siblings = Array.from(parent.children)
          .filter((item) => item.nodeName === current.nodeName);
        if (siblings.length > 1) part += `:nth-of-type(${siblings.indexOf(current) + 1})`;
      }
      parts.unshift(part);
      current = parent;
    }
    return parts.join(" > ");
  };
  const textByIdRefs = (ids) => norm(String(ids || "").split(/\s+/).map((id) => {
    const target = document.getElementById(id);
    return target ? target.innerText || target.textContent || "" : "";
  }).join(" "));
  const explicitLabel = (el) => {
    if (el.id) {
      const label = document.querySelector(`label[for="${esc(el.id)}"]`);
      if (label) return norm(label.innerText || label.textContent || "");
    }
    const wrapped = el.closest("label");
    if (wrapped) return norm(wrapped.innerText || wrapped.textContent || "");
    return "";
  };
  const bestLabel = (el) => norm([
    explicitLabel(el),
    el.getAttribute("aria-label"),
    textByIdRefs(el.getAttribute("aria-labelledby")),
    el.getAttribute("placeholder")
  ].find(Boolean) || "");
  const nearbyText = (el) => {
    const parent = el.closest("label, div, li, p, td, section, fieldset") || el.parentElement;
    return norm(parent ? (parent.innerText || parent.textContent || "").slice(0, 500) : "");
  };
  const sectionText = (el) => {
    const fieldset = el.closest("fieldset");
    if (fieldset) {
      const legend = fieldset.querySelector("legend");
      if (legend) return norm(legend.innerText || legend.textContent || "");
    }
    const section = el.closest("section, form, article, main");
    if (!section) return "";
    const heading = section.querySelector("h1,h2,h3,h4,[role='heading']");
    return norm(heading ? heading.innerText || heading.textContent || "" : "");
  };
  const required = (el) => {
    const label = bestLabel(el);
    const nearby = nearbyText(el);
    return !!el.required
      || el.getAttribute("aria-required") === "true"
      || /\*\s*$/.test(label)
      || /\*\s*$/.test(nearby);
  };
  const optionLabel = (input) => norm(explicitLabel(input) || input.value);
  const add = (el, extra) => {
    if (!visible(el)) return;
    const label = extra.label_override || bestLabel(el);
    fields.push({
      selector: extra.selector || cssPath(el),
      element_type: extra.element_type,
      input_type: extra.input_type || null,
      label_text: label,
      nearby_text: nearbyText(el),
      section_text: sectionText(el),
      name: el.getAttribute("name"),
      id_attribute: el.getAttribute("id"),
      autocomplete: el.getAttribute("autocomplete"),
      placeholder: el.getAttribute("placeholder"),
      options: extra.options || [],
      current_value: extra.current_value ?? el.value ?? "",
      required: required(el),
      confidence_notes: extra.confidence_notes || []
    });
  };

  const grouped = Array.from(
    document.querySelectorAll("input[type='radio'],input[type='checkbox']")
  );
  for (const input of grouped) {
    if (!visible(input)) continue;
    const fieldset = input.closest("fieldset");
    const key = [
      input.type,
      input.name,
      fieldset ? sectionText(input) : "",
      input.form ? input.form.id : ""
    ].join("|");
    if (seenGroups.has(key)) continue;
    seenGroups.add(key);
    const members = grouped.filter((candidate) => {
      const candidateFieldset = candidate.closest("fieldset");
      const candidateKey = [
        candidate.type,
        candidate.name,
        candidateFieldset ? sectionText(candidate) : "",
        candidate.form ? candidate.form.id : ""
      ].join("|");
      return candidateKey === key && visible(candidate);
    });
    const legend = fieldset ? fieldset.querySelector("legend") : null;
    add(input, {
      element_type: input.type === "radio" ? "radio" : "checkbox",
      input_type: input.type,
      label_override: legend ? norm(legend.innerText || legend.textContent || "") : "",
      selector: input.name
        ? `input[type="${input.type}"][name="${esc(input.name)}"]`
        : cssPath(input),
      options: members.map(optionLabel).filter(Boolean),
      current_value: members.filter((member) => member.checked).map(optionLabel).join(", "),
      confidence_notes: ["Grouped by type, name, fieldset legend, and form id."],
    });
  }

  for (const el of Array.from(document.querySelectorAll("input, textarea, select"))) {
    if (!visible(el)) continue;
    if (el.matches("input[type='radio'],input[type='checkbox'],input[type='hidden']")) continue;
    if (el.tagName.toLowerCase() === "select") {
      add(el, {
        element_type: "select",
        input_type: "select-one",
        options: Array.from(el.options).map((option) => norm(option.text)).filter(Boolean)
      });
    } else if (el.tagName.toLowerCase() === "textarea") {
      add(el, { element_type: "textarea", input_type: "textarea" });
    } else {
      add(el, { element_type: "input", input_type: el.type || "text" });
    }
  }

  for (const el of Array.from(document.querySelectorAll(
    "button,input[type='submit'],input[type='button'],input[type='reset']"
  ))) {
    if (!visible(el)) continue;
    add(el, {
      element_type: "button",
      input_type: el.type || "button",
      current_value: norm(el.innerText || el.value || el.textContent || "")
    });
  }

  for (const el of Array.from(document.querySelectorAll("[role='combobox'],[role='listbox']"))) {
    if (!visible(el)) continue;
    const role = el.getAttribute("role");
    add(el, {
      element_type: role,
      input_type: role,
      current_value: norm(el.innerText || el.textContent || ""),
      confidence_notes: ["ARIA custom widget detected; automatic fill support is limited."]
    });
  }

  return fields;
}
"""


def scan_page(page: Page) -> list[DetectedField]:
    detections: list[DetectedField] = []
    for frame_index, frame in enumerate(page.frames):
        try:
            raw_fields = frame.evaluate(SCAN_SCRIPT)
        except Exception:
            continue
        for local_index, raw in enumerate(raw_fields):
            if not isinstance(raw, dict):
                continue
            raw["frame_index"] = frame_index
            raw["frame_url"] = frame.url
            raw["stable_id"] = make_stable_id(frame_index, local_index, raw)
            detections.append(DetectedField.model_validate(raw))
    return detections


def make_stable_id(frame_index: int, local_index: int, raw: dict[str, Any]) -> str:
    seed = "|".join(
        [
            str(frame_index),
            str(local_index),
            raw.get("selector") or "",
            raw.get("label_text") or "",
            raw.get("name") or "",
            raw.get("id_attribute") or "",
        ]
    )
    return "field-" + hashlib.sha1(seed.encode("utf-8")).hexdigest()[:12]
