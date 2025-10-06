# app.py — ApPlautus (logic-only; styles live in styles.css)
from __future__ import annotations
import json
import re
from pathlib import Path
from typing import Any, Dict, List, Tuple
import streamlit as st

# ---------------- Config & Paths ----------------
APP_FOLDER = Path(__file__).parent.resolve()
VERSES_DIR = APP_FOLDER / "verses_jsons"  # strict folder per your request
CSS_PATH = APP_FOLDER / "styles.css"
FILE_PATTERN = re.compile(r"^\s*(\d+)_word_syllable_verse-mask_metre-matching\.json$", re.IGNORECASE)

st.set_page_config(page_title="ApPlautus", page_icon="📜", layout="wide")

# ---------------- Utils ----------------
def inject_css(path: Path) -> None:
    try:
        css = path.read_text(encoding="utf-8")
        st.markdown(f"<style>{css}</style>", unsafe_allow_html=True)
    except Exception as e:
        st.warning(f"Could not load CSS from {path.name}: {e}")

def html_escape(s: str) -> str:
    return str(s).replace("&","&amp;").replace("<","&lt;").replace(">","&gt;")

# inject external CSS
inject_css(CSS_PATH)

# ---------------- Helpers ----------------
def list_json_files() -> List[Path]:
    """Only files matching <number>_word_syllable_verse-mask_metre-matching.json in ./verses_jsons/"""
    VERSES_DIR.mkdir(parents=True, exist_ok=True)
    matched = []
    for p in VERSES_DIR.iterdir():
        if p.is_file() and FILE_PATTERN.match(p.name):
            matched.append(p)
    matched.sort(key=lambda p: int(FILE_PATTERN.match(p.name).group(1)))
    return matched

def load_json(path: Path) -> Dict[str, Any]:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)

def idx_by_num(items: List[Dict[str, Any]], key: str) -> Dict[int, Dict[str, Any]]:
    out: Dict[int, Dict[str, Any]] = {}
    for it in items or []:
        n = it.get(key)
        if isinstance(n, (int, float)):
            out[int(n)] = it
    return out

def mask_candidates(data: Dict[str, Any]) -> List[Dict[str, Any]]:
    masks = (data.get("prosodic_masks") or {}).get("masks") or []
    return [m for m in masks if (m.get("verse_type") is not None and str(m.get("verse_type")).strip() != "")]

def mask_to_dash_u(mask_str: str) -> str:
    # l/L -> '-', s/S -> 'u'
    return "".join("-" if ch in "lL" else "u" if ch in "sS" else ch for ch in str(mask_str))

def bool_strict(val: Any) -> bool:
    """Boolean-ish coercion that handles True/False, 1/0, and 'true'/'false' strings."""
    if isinstance(val, bool):
        return val
    if isinstance(val, (int, float)):
        return val != 0
    if isinstance(val, str):
        v = val.strip().lower()
        if v in {"true", "1", "yes", "y"}:
            return True
        if v in {"false", "0", "no", "n", ""}:
            return False
    return False

def reconstruct_units(
    data: Dict[str, Any], mask: Dict[str, Any]
) -> Tuple[List[Dict[str, Any]], List[int], List[int], str, str, List[int], List[int]]:
    """Return (units, ictus_positions, accent_positions, mask_ls, mask_du, foot_after, hiatus_after)."""
    words = data.get("words") or []
    words_by = idx_by_num(words, "word_number")

    seq = mask.get("word-variant") or []
    units: List[Dict[str, Any]] = []
    for pair in seq:
        wnum = int(pair.get("word"))
        vnum = int(pair.get("variant"))
        w = words_by.get(wnum)
        if not w:
            units.append({"word_number": wnum, "variant_number": vnum, "word_text": f"[missing word #{wnum}]", "syllables": []})
            continue
        variants = w.get("variants") or []
        v_by = idx_by_num(variants, "variant_number")
        v = v_by.get(vnum)
        if not v:
            units.append({"word_number": wnum, "variant_number": vnum, "word_text": f"{w.get('text','[word]')}[missing variant #{vnum}]", "syllables": []})
            continue
        sylls = (v.get("syllables") or [])
        # Ensure sort by syllable_number + normalize bools
        sylls_sorted = sorted(sylls, key=lambda s: int(s.get("syllable_number", 10**9)))
        for s in sylls_sorted:
            s["elision"] = bool_strict(s.get("elision", False))
            s["length"]  = bool_strict(s.get("length", False))
        units.append({"word_number": wnum, "variant_number": vnum, "word_text": w.get("text",""), "syllables": sylls_sorted})

    ict = [int(i) for i in (mask.get("icted_syllables") or []) if isinstance(i, (int, float))]
    acc = [int(i) for i in (mask.get("accented_syllables") or []) if isinstance(i, (int, float))]
    mask_ls = str(mask.get("prosodic_mask", ""))           # original l/s
    mask_du = mask_to_dash_u(mask_ls)                      # converted -/u
    foot_after   = [int(i) for i in (mask.get("foot_boundary_after") or []) if isinstance(i, (int, float))]
    hiatus_after = [int(i) for i in (mask.get("hiatus_after") or []) if isinstance(i, (int, float))]
    return units, ict, acc, mask_ls, mask_du, foot_after, hiatus_after

def render_units(
    units: List[Dict[str, Any]],
    ictus_positions: List[int],
    accent_positions: List[int],
    foot_after: List[int],
    hiatus_after: List[int],
) -> str:
    """
    Two aligned rows per syllable column:
      - top row: '-' (long) or 'u' (short) from syllable.length
      - bottom: syllable chip; ictus = light red bg; both accent+ictus = light green bg
      - accent tick is a vertical line above (via .accent)
      - elision: grey and ignored in counting ONLY if this variant's elision==True
        AND its candidate effective index is NOT in hiatus_after (hiatus forces non-elision).
      - foot boundaries: thin vertical lines after the given effective indices (ignoring elided syllables)
    """
    parts: List[str] = []
    eff_idx = 0  # effective syllable index (ignoring elisions per rule above)

    parts.append('<div class="ap-verse">')
    for ui, unit in enumerate(units):
        if ui > 0:
            parts.append('<span class="word-gap"></span>')
        if not unit["syllables"]:
            parts.append(
                f'<div class="syl-col"><div class="syl-mark">&nbsp;</div>'
                f'<span class="syl" title="No syllables for word #{unit["word_number"]}, variant #{unit["variant_number"]}">'
                f'{html_escape(unit["word_text"])}</span></div>'
            )
            continue

        for syl in unit["syllables"]:
            default_elide = bool_strict(syl.get("elision", False))
            is_long       = bool_strict(syl.get("length", False))

            # candidate effective index if we count this syllable
            candidate_idx = eff_idx + 1

            # hiatus override: if candidate index is in hiatus_after, force non-elision
            is_elide = default_elide and (candidate_idx not in hiatus_after)

            # marker above: only for non-elided
            mark_char = "-" if (is_long and not is_elide) else ("u" if (not is_long and not is_elide) else "&nbsp;")

            classes = ["syl"]
            title_bits = []

            if not is_elide:
                eff_idx += 1  # count this syllable

                is_accent = (eff_idx in accent_positions)
                is_ictus  = (eff_idx in ictus_positions)

                # background color class
                if is_accent and is_ictus:
                    classes.append("both")   # green background
                    classes.append("accent") # keep vertical tick
                    title_bits += ["accent", "ictus"]
                elif is_accent:
                    classes.append("accent") # tick only
                    title_bits.append("accent")
                elif is_ictus:
                    classes.append("icted")  # light red background
                    title_bits.append("ictus")

                title_bits.append("long" if is_long else "short")
            else:
                classes.append("elide")
                title_bits.append("elision")

            # render the syllable column
            parts.append(
                f'<div class="syl-col">'
                f'  <div class="syl-mark">{mark_char}</div>'
                f'  <span class="{" ".join(classes)}" title="{html_escape(", ".join(title_bits) or "syllable")}">{html_escape(syl.get("text",""))}</span>'
                f'</div>'
            )

            # foot boundary AFTER this effective syllable?
            if (not is_elide) and (eff_idx in foot_after):
                parts.append('<span class="foot-divider"></span>')

    parts.append('</div>')
    return "".join(parts)

# ---------------- Sidebar: list verses (clickable) ----------------
with st.sidebar:
    st.markdown('<h1 class="ap-title">ApPlautus</h1>', unsafe_allow_html=True)

    files = list_json_files()
    if not files:
        st.info("Place files like `2_word_syllable_verse-mask_metre-matching.json` in `./verses_jsons/`.")
        st.stop()

    verses: List[Tuple[int, str, Path]] = []
    for p in files:
        m = FILE_PATTERN.match(p.name)
        num = int(m.group(1)) if m else 10**9
        try:
            data_preview = load_json(p)
            verse_text = str(data_preview.get("verse", "")).strip()
        except Exception:
            verse_text = ""
        verses.append((num, verse_text, p))

    if "current_idx" not in st.session_state:
        st.session_state["current_idx"] = 0

    # No "Poem" heading
    for i, (num, vtext, path) in enumerate(verses):
        label = f"{num:03d} — {vtext}"
        with st.container():
            st.markdown('<div class="sidebar-verse">', unsafe_allow_html=True)
            if st.button(label, key=f"verse_line_{i}"):
                st.session_state["current_idx"] = i
            st.markdown('</div>', unsafe_allow_html=True)

current_path = verses[st.session_state["current_idx"]][2]

# ---------------- Load selected verse ----------------
try:
    data = load_json(current_path)
except Exception as e:
    st.error(f"Failed to load JSON: {current_path.name}\n\n{e}")
    st.stop()

# ---------------- Verse fulltext (centered) ----------------
st.markdown(
    f'<div class="ap-verse-header"><div class="text">{html_escape(data.get("verse","(no verse text)"))}</div></div>',
    unsafe_allow_html=True
)

# Collatinus (left-aligned)
st.markdown(
    f'<div class="ap-meta"><b>Collatinus scansion:</b> {html_escape(data.get("collatinus_scan","—"))}<br>'
    f'<b>Collatinus accentuation:</b> {html_escape(data.get("collatinus_accentuate","—"))}</div>',
    unsafe_allow_html=True
)

# Spacer before metrics row
st.markdown('<div class="spacer-before-metrics"></div>', unsafe_allow_html=True)

# ---------------- Prosodic masks: TOTAL count (metric) + plain list ----------------
all_masks = (data.get("prosodic_masks") or {}).get("masks") or []
total_mask_count = len(all_masks)

left, right = st.columns([1, 3])
with left:
    wc = int(data.get("word_count", 0)) if isinstance(data.get("word_count"), (int, float)) else 0
    st.metric("Words", wc)
with right:
    st.metric("Prosodic masks", total_mask_count)

def mask_label_in_list(m: Dict[str, Any]) -> str:
    mn = int(m.get("mask_number", -1)) if isinstance(m.get("mask_number"), (int, float)) else -1
    vt = str(m.get("verse_type", "—")).strip() or "—"
    pm_ls = str(m.get("prosodic_mask", ""))
    pm_du = mask_to_dash_u(pm_ls)
    sc = int(m.get("syllable_count", 0)) if isinstance(m.get("syllable_count"), (int, float)) else 0
    return f"#{mn} • {vt} • {pm_ls} / {pm_du} • {sc}"

st.markdown(
    '<div class="mask-list">' +
    "".join(f"<div>{html_escape(mask_label_in_list(m))}</div>" for m in all_masks) +
    "</div>",
    unsafe_allow_html=True
)

# ---------------- Mask selection (only verse_type not null) — no heading ----------------
cands = mask_candidates(data)
if not cands:
    st.warning("No prosodic masks with a non-null `verse_type` found.")
    st.stop()

if "mask_idx" not in st.session_state:
    st.session_state["mask_idx"] = 0

cols_per_row = 3
rows = (len(cands) + cols_per_row - 1) // cols_per_row
btn_index = 0
for _ in range(rows):
    cols = st.columns(cols_per_row, gap="small")
    for c in cols:
        if btn_index >= len(cands):
            break
        m = cands[btn_index]
        pm_ls = str(m.get("prosodic_mask", ""))
        pm_du = mask_to_dash_u(pm_ls)
        vt = str(m.get("verse_type", "—")).strip() or "—"
        lbl = f"{vt} • {pm_ls} / {pm_du}"
        if c.button(lbl, key=f"mask_btn_{btn_index}", use_container_width=True):
            st.session_state["mask_idx"] = btn_index
        btn_index += 1

mask = cands[st.session_state["mask_idx"]]

# ---------------- Reconstruction (markers above; elision+hiatus rules; foot boundaries) ----------------
units, ictus_positions, accent_positions, mask_ls, mask_du, foot_after, hiatus_after = reconstruct_units(data, mask)
st.markdown(
    render_units(units, ictus_positions, accent_positions, foot_after, hiatus_after),
    unsafe_allow_html=True
)

# ---------------- Details (always open) ----------------
with st.expander("Details", expanded=True):
    colA, colB = st.columns(2)
    with colA:
        st.write("**Mask**")
        st.code(mask_ls, language="text")
        st.code(mask_du, language="text")
        st.write("**Verse type:**", mask.get("verse_type","—"))
    with colB:
        ict = ", ".join(str(int(x)) for x in (mask.get("icted_syllables") or [])) or "—"
        acc = ", ".join(str(int(x)) for x in (mask.get("accented_syllables") or [])) or "—"
        inter = mask.get("accent_ictus_intersection", "—")
        st.write("**Ictus positions:**", ict)
        st.write("**Accented positions:**", acc)
        st.write("**Accent ∩ Ictus:**", inter)
        st.write("**Foot boundaries after:**", ", ".join(map(str, foot_after)) or "—")
        st.write("**Syllable count:**", mask.get("syllable_count", "—"))

# ---------------- Footer ----------------
st.markdown('<div class="ap-footer">© Jakub Kozák, 2025</div>', unsafe_allow_html=True)