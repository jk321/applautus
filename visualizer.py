# app.py — ApPlautus
from __future__ import annotations
import json
import re
from pathlib import Path
from typing import Any, Dict, List, Tuple
import streamlit as st

# ---------------- Config & Paths ----------------
APP_FOLDER = Path(__file__).parent.resolve()
VERSES_DIR = APP_FOLDER / "verses_jsons"  # per request
FILE_PATTERN = re.compile(r"^\s*(\d+)_word_syllable_verse-mask_metre-matching\.json$", re.IGNORECASE)

st.set_page_config(page_title="ApPlautus", page_icon="📜", layout="wide")

# ---------------- Styles ----------------
st.markdown(
    """
<style>
/* Sidebar slightly narrower (single-line verse buttons) */
[data-testid="stSidebar"] {
  min-width: 440px !important;
  width: 440px !important;
}
section[data-testid="stSidebar"] .block-container { padding-top: .6rem; }

/* Hide Streamlit's Deploy toolbar */
header[data-testid="stHeader"] div[data-testid="stToolbar"] { display: none !important; }

/* Sidebar verse "lines" like poem; single line, no wrap */
.sidebar-verse button {
  background: transparent !important;
  border: none !important;
  color: #1f2937 !important;
  text-align: left !important;
  padding: .25rem .25rem !important;
  border-radius: .25rem !important;
  font-size: 1rem !important;
  line-height: 1.15 !important;
  white-space: nowrap !important;
  overflow: hidden !important;
  text-overflow: ellipsis !important;
}
.sidebar-verse button:hover {
  background: rgba(0,0,0,.06) !important;
}

/* Centered BIG verse text (no heading) */
.ap-verse-header {
  display: flex;
  justify-content: center;
  margin-top: .25rem;
}
.ap-verse-header .text {
  font-size: 1.6rem;
  line-height: 1.4;
  text-align: center;
}

/* Collatinus meta: left-aligned + larger top margin */
.ap-meta {
  text-align: left;
  color:#555;
  margin: 1rem auto 0 auto; /* bigger vertical space above */
  max-width: 1100px;
}

/* Spacer before metrics (Words / Prosodic masks) */
.spacer-before-metrics { height: 1.25rem; }

/* Reconstruction: centered & bigger, markers above; extra bottom margin before Details */
.ap-verse {
  display:flex;
  justify-content:center;
  align-items:flex-start;
  flex-wrap:wrap;
  gap:.6rem 1.0rem;            /* syllables within same word slightly closer */
  padding:1.1rem 1rem 0 1rem;
  margin-bottom: 1.75rem;      /* bigger vertical space before Details */
}

/* One syllable column: marker above, chip below */
.syl-col {
  display:flex;
  flex-direction:column;
  align-items:center;
  gap:.2rem;
}

/* Marker row above syllable: shows '-' or 'u' */
.syl-mark {
  font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, "Liberation Mono", "Courier New", monospace;
  font-size: 1.25rem;
  line-height: 1;
  color: #444;
}

/* The syllable chip itself (simple, no backgrounds) */
.syl {
  position: relative;
  display:inline-block;
  padding:.25rem .50rem;
  margin:0;
  border:1px solid rgba(0,0,0,.30);
  border-radius:.50rem;
  background:#fff;
  line-height:1.2;
  font-family: ui-sans-serif, system-ui, -apple-system, "Segoe UI", Roboto, Ubuntu, Helvetica, Arial;
  font-size: 1.3rem;
  color:#222;
  white-space: nowrap;
}

/* Accent: vertical tick above the chip */
.syl.accent::before {
  content:"";
  position:absolute;
  top:-10px;
  left:50%;
  transform:translateX(-50%);
  height:12px;
  border-left:2px solid currentColor;
}

/* Ictus syllables in red */
.syl.icted { color:#c62828; }

/* BOTH (accent & ictus): green, still shows the accent tick */
.syl.both { color:#2e7d32; }  /* green */

/* Elision syllables: muted (gray), no markers/ticks handled in HTML */
.syl.elide { color:#888; }

/* Clear separation between words (slightly larger than intra-word spacing) */
.word-gap { display:inline-block; width:1.6rem; height:1px; }

/* Plain mask list (no hover), with extra bottom margin */
.mask-list {
  display:grid;
  grid-template-columns:1fr 1fr;
  gap:.35rem .5rem;
  margin-top:.5rem;
  margin-bottom: 1.25rem;  /* bigger space after masks */
  font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, "Courier New", monospace;
  font-size:.95rem;
  color:#333;
  white-space:nowrap;
}

/* Footer */
.ap-footer { text-align:center; margin:2rem 0 .5rem 0; color:#666; font-size:.9rem; }
</style>
""",
    unsafe_allow_html=True
)

# ---------------- Helpers ----------------
def list_json_files() -> List[Path]:
    """
    Return only files that match:
    <number>_word_syllable_verse-mask_metre-matching.json
    in ./verses_jsons/
    """
    VERSES_DIR.mkdir(parents=True, exist_ok=True)
    matched = []
    for p in VERSES_DIR.iterdir():
        if not p.is_file():
            continue
        m = FILE_PATTERN.match(p.name)
        if not m:
            continue
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

def reconstruct_units(
    data: Dict[str, Any], mask: Dict[str, Any]
) -> Tuple[List[Dict[str, Any]], List[int], List[int], str, str]:
    """Return (units, ictus_positions, accent_positions, mask_ls, mask_du)."""
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
        sylls_sorted = sorted(sylls, key=lambda s: int(s.get("syllable_number", 10**9)))
        units.append({"word_number": wnum, "variant_number": vnum, "word_text": w.get("text",""), "syllables": sylls_sorted})

    ict = [int(i) for i in (mask.get("icted_syllables") or []) if isinstance(i, (int, float))]
    acc = [int(i) for i in (mask.get("accented_syllables") or []) if isinstance(i, (int, float))]
    mask_ls = str(mask.get("prosodic_mask", ""))           # original l/s
    mask_du = mask_to_dash_u(mask_ls)                      # converted -/u
    return units, ict, acc, mask_ls, mask_du

def html_escape(s: str) -> str:
    return str(s).replace("&","&amp;").replace("<","&lt;").replace(">","&gt;")

def render_units(units: List[Dict[str, Any]], ictus_positions: List[int], accent_positions: List[int]) -> str:
    """
    Two aligned rows per syllable column:
      - top row: '-' for long or 'u' for short (from syllable.length)
      - bottom: syllable chip; red if ictus; vertical tick if accented
      - BOTH (accent & ictus): green (with accent tick)
      - if syllable.elision==True: no '-', no tick, not red/green, chip in gray
    """
    parts: List[str] = []
    global_idx = 0  # 1-based position across the verse

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
            global_idx += 1
            is_elide = bool(syl.get("elision"))
            is_long = bool(syl.get("length"))
            mark_char = "-" if (is_long and not is_elide) else ("u" if (not is_long and not is_elide) else "&nbsp;")

            classes = ["syl"]
            title_bits = []
            if not is_elide:
                title_bits.append("long" if is_long else "short")

                is_accent = (global_idx in accent_positions)
                is_ictus = (global_idx in ictus_positions)

                if is_accent and is_ictus:
                    classes.append("both")   # green
                    classes.append("accent") # keep tick
                    title_bits += ["accent", "ictus"]
                elif is_accent:
                    classes.append("accent")
                    title_bits.append("accent")
                elif is_ictus:
                    classes.append("icted")  # red
                    title_bits.append("ictus")
            else:
                classes.append("elide")
                title_bits.append("elision")

            parts.append(
                f'<div class="syl-col">'
                f'  <div class="syl-mark">{mark_char}</div>'
                f'  <span class="{" ".join(classes)}" title="{html_escape(", ".join(title_bits) or "syllable")}">{html_escape(syl.get("text",""))}</span>'
                f'</div>'
            )

    parts.append('</div>')
    return "".join(parts)

# ---------------- Sidebar: list verses (clickable) ----------------
with st.sidebar:
    st.title("ApPlautus")

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

# Collatinus (left-aligned, with bigger top margin via CSS)
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

# Plain list of all masks (informational)
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

# Buttons grid
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

# ---------------- Reconstruction (centered & bigger; markers above; elision & BOTH rules) ----------------
units, ictus_positions, accent_positions, mask_ls, mask_du = reconstruct_units(data, mask)
st.markdown(render_units(units, ictus_positions, accent_positions), unsafe_allow_html=True)

# ---------------- Details (always open) ----------------
with st.expander("Details", expanded=True):
    colA, colB = st.columns(2)
    with colA:
        st.write("**Mask**")
        # Show both representations under one heading
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
        st.write("**Syllable count:**", mask.get("syllable_count", "—"))

# ---------------- Footer ----------------
st.markdown('<div class="ap-footer">© Jakub Kozák, 2025</div>', unsafe_allow_html=True)
