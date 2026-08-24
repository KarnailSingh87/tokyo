"""
LinkedIn Profile Auto-Updater.

Flow:
  1. Locate a resume file (explicit path or auto-find recent resume/cv in common folders).
  2. Extract raw text (PDF via pdfplumber/pypdf, DOCX via python-docx, plain text).
  3. Ask Gemini to turn the raw text into polished, structured LinkedIn content.
  4. Apply it to the user's LinkedIn profile with a real browser session (Playwright).
     First run opens a visible browser window so the user can log in once;
     the session cookie is persisted and reused afterwards.

Never handles credentials itself — login is always typed by the user in the window.
"""

from __future__ import annotations

import json
import re
import time
import zipfile
import xml.etree.ElementTree as ET
from pathlib import Path
from datetime import datetime

BASE_DIR = Path(__file__).resolve().parent.parent
CONFIG_DIR = BASE_DIR / "config"
MEMORY_DIR = BASE_DIR / "memory"
PROFILE_CACHE = MEMORY_DIR / "linkedin_latest.json"
BROWSER_DATA_DIR = CONFIG_DIR / "linkedin_profile"

RESUME_NAME_RE = re.compile(r"(resume|cv|curriculum)", re.IGNORECASE)
SEARCH_DIRS = [
    BASE_DIR / "workspace",
    Path.home() / "Downloads" / "TOKYO Uploads",
    Path.home() / "Downloads",
    Path.home() / "Desktop",
    Path.home() / "Documents",
]

VALID_SECTIONS = ["headline", "about", "skills", "experience", "education"]


def _get_api_key() -> str:
    with open(CONFIG_DIR / "api_keys.json", "r", encoding="utf-8") as f:
        return json.load(f)["gemini_api_key"]


def _gemini_generate(prompt: str) -> str:
    from concurrent.futures import ThreadPoolExecutor
    from google import genai

    client = genai.Client(api_key=_get_api_key())
    models = ["gemini-flash-latest", "gemini-2.0-flash", "gemini-2.5-flash"]
    last_err: Exception | None = None
    with ThreadPoolExecutor(max_workers=1) as pool:
        for model in models:
            for attempt in range(2):
                fut = pool.submit(lambda m=model: client.models.generate_content(model=m, contents=prompt))
                try:
                    resp = fut.result(timeout=30)
                    if resp.text:
                        return resp.text
                except Exception as e:
                    last_err = e
                    time.sleep(1)
    raise RuntimeError(f"AI analysis unavailable after retries: {last_err}")


# ── Resume discovery ─────────────────────────────────────────────────────────


def _find_resume(explicit: str | None) -> Path:
    if explicit:
        p = Path(explicit).expanduser()
        if not p.exists():
            raise FileNotFoundError(f"File not found: {p}")
        return p

    candidates: list[tuple[float, Path]] = []
    for d in SEARCH_DIRS:
        if not d.is_dir():
            continue
        for f in d.iterdir():
            if not f.is_file() or f.suffix.lower() not in (".pdf", ".docx", ".doc", ".txt", ".md"):
                continue
            if RESUME_NAME_RE.search(f.stem):
                candidates.append((f.stat().st_mtime, f))
    if not candidates:
        raise FileNotFoundError(
            "No resume found. Put your resume (named with 'resume' or 'cv' in the filename) "
            "in Downloads, Desktop or Documents, or tell me its full path."
        )
    return max(candidates, key=lambda t: t[0])[1]


# ── Text extraction ──────────────────────────────────────────────────────────


def _extract_pdf_text(path: Path) -> str:
    try:
        import pdfplumber

        parts = []
        with pdfplumber.open(str(path)) as pdf:
            for page in pdf.pages:
                parts.append(page.extract_text() or "")
        text = "\n".join(parts)
        if text.strip():
            return text
    except Exception:
        pass
    from pypdf import PdfReader

    reader = PdfReader(str(path))
    return "\n".join((page.extract_text() or "") for page in reader.pages)


def _extract_docx_text(path: Path) -> str:
    try:
        import docx  # type: ignore

        document = docx.Document(str(path))
        return "\n".join(p.text for p in document.paragraphs if p.text.strip())
    except Exception:
        pass
    # Fallback: parse the raw OOXML ourselves (no dependency needed)
    ns = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"}
    with zipfile.ZipFile(str(path)) as z:
        xml_bytes = z.read("word/document.xml")
    root = ET.fromstring(xml_bytes)
    paragraphs = []
    for para in root.iter(f"{{{ns['w']}}}p"):
        texts = [t.text or "" for t in para.iter(f"{{{ns['w']}}}t")]
        line = "".join(texts).strip()
        if line:
            paragraphs.append(line)
    return "\n".join(paragraphs)


def _extract_text(path: Path) -> str:
    ext = path.suffix.lower()
    if ext == ".pdf":
        return _extract_pdf_text(path)
    if ext in (".docx",):
        return _extract_docx_text(path)
    if ext == ".doc":
        raise ValueError("Legacy .doc is not supported — save it as .pdf or .docx first.")
    return path.read_text(encoding="utf-8", errors="ignore")


# ── Gemini analysis ──────────────────────────────────────────────────────────

_ANALYSIS_PROMPT = """You are an expert LinkedIn profile writer.
Below is the raw text of a person's resume/CV.

Transform it into polished LinkedIn profile content. Rules:
- Write in first person for the About section, professional but warm, 3 short paragraphs max (~1200 chars).
- Headline: max 220 chars, format "Role @ Company | key skill • key skill • value proposition". No emojis.
- Experience: one entry per role found. Dates exactly as in the resume ("Jan 2020 – Present" style).
- Skills: 5-15 concise skill names.
- Education: one entry per degree.
- Use ONLY facts present in the resume. Do not invent employers, dates or numbers.
- Respond with ONLY a valid JSON object, no markdown fences, matching exactly this schema:
{{
  "name": "...",
  "headline": "...",
  "about": "...",
  "experience": [{{"title": "...", "company": "...", "dates": "...", "description": "2-3 sentence achievement-focused summary"}}],
  "education": [{{"school": "...", "degree": "...", "dates": "..."}}],
  "skills": ["..."]
}}

Sections requested by the user: {sections}. For sections NOT requested you may leave them empty ([] or ""), but still include all keys.

RESUME TEXT:
<<<
{text}
>>>"""


def _analyze_resume(text: str, sections: list[str]) -> dict:
    prompt = _ANALYSIS_PROMPT.format(sections=", ".join(sections), text=text[:60000])
    raw = _gemini_generate(prompt)
    m = re.search(r"\{[\s\S]*\}", raw)
    if not m:
        raise ValueError("Gemini did not return structured content.")
    data = json.loads(m.group(0))
    data["_meta"] = {
        "source_file": None,
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "sections": sections,
    }
    return data


def _load_cache() -> dict | None:
    try:
        return json.loads(PROFILE_CACHE.read_text(encoding="utf-8"))
    except Exception:
        return None


def _save_cache(data: dict, source: Path | None) -> None:
    PROFILE_CACHE.parent.mkdir(exist_ok=True)
    data.setdefault("_meta", {})["source_file"] = str(source) if source else None
    data["_meta"]["cached_at"] = datetime.now().isoformat(timespec="seconds")
    PROFILE_CACHE.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")


# ── Browser automation ───────────────────────────────────────────────────────


def _launch_browser(headless: bool):
    from playwright.sync_api import sync_playwright

    pw = sync_playwright().start()
    BROWSER_DATA_DIR.mkdir(parents=True, exist_ok=True)
    context = pw.chromium.launch_persistent_context(
        user_data_dir=str(BROWSER_DATA_DIR),
        headless=headless,
        viewport={"width": 1280, "height": 900},
        args=["--disable-blink-features=AutomationControlled"],
    )
    page = context.pages[0] if context.pages else context.new_page()
    return pw, context, page


def _is_logged_in(page) -> bool:
    try:
        page.goto("https://www.linkedin.com/feed/", wait_until="domcontentloaded", timeout=30_000)
        url = page.url
        if "/login" in url or "checkpoint" in url or "authwall" in url:
            return False
        page.wait_for_selector("button[aria-label*='Me'], img.global-nav__me-photo", timeout=10_000)
        return True
    except Exception:
        return False


def _wait_for_manual_login(page, player=None, timeout_s: int = 240) -> bool:
    if player:
        player.write_log("SYS: LinkedIn login needed — complete it in the opened browser window.")
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        if _is_logged_in(page):
            return True
        time.sleep(3)
    return False


def _click_first(page, selectors: list[str], timeout_ms: int = 6000) -> bool:
    for sel in selectors:
        try:
            loc = page.locator(sel).first
            loc.wait_for(state="visible", timeout=timeout_ms)
            loc.click()
            return True
        except Exception:
            continue
    return False


def _update_headline(page, headline: str) -> str:
    page.goto("https://www.linkedin.com/in/me/", wait_until="domcontentloaded", timeout=40_000)
    page.wait_for_timeout(2500)
    if not _click_first(
        page,
        [
            "button[aria-label*='Edit intro' i]",
            "button[aria-label*='edit intro' i]",
            "div.ph0.pv-top-card button.pvs-profile-actions__action:has-text('Edit')",
            "button:has(svg use[href*='pencil']) >> nth=0",
        ],
        timeout_ms=8000,
    ):
        return "headline: could not open the Edit intro dialog"
    page.wait_for_timeout(1500)

    filled = False
    for sel in ["input[name='headline']", "input[id*='headline' i]", "textarea[name='headline']"]:
        try:
            field = page.locator(sel).first
            field.wait_for(state="visible", timeout=4000)
            field.fill("")
            field.type(headline, delay=15)
            filled = True
            break
        except Exception:
            continue
    if not filled:
        return "headline: dialog opened but the input field was not found"
    if not _click_first(page, ["button:has-text('Save')"]):
        return "headline: could not press Save"
    page.wait_for_timeout(2000)
    return "headline: updated"


def _update_about(page, about: str) -> str:
    page.goto("https://www.linkedin.com/in/me/details/about/", wait_until="domcontentloaded", timeout=40_000)
    page.wait_for_timeout(2500)
    if not _click_first(
        page,
        [
            "button[aria-label*='Edit about' i]",
            "section:has-text('About') button:has(svg use[href*='pencil'])",
        ],
    ):
        return "about: could not open the About editor"
    page.wait_for_timeout(1500)

    filled = False
    for sel in ["textarea[name='summary']", "textarea[id*='summary' i]", "div[data-test-about-editor] textarea"]:
        try:
            field = page.locator(sel).first
            field.wait_for(state="visible", timeout=4000)
            field.fill("")
            field.type(about, delay=5)
            filled = True
            break
        except Exception:
            continue
    if not filled:
        return "about: editor opened but the textarea was not found"
    if not _click_first(page, ["button:has-text('Save')"]):
        return "about: could not press Save"
    page.wait_for_timeout(2000)
    return "about: updated"


def _add_skills(page, skills: list[str]) -> str:
    added, failed = [], []
    for skill in skills[:10]:
        page.goto("https://www.linkedin.com/in/me/details/skills/", wait_until="domcontentloaded", timeout=40_000)
        page.wait_for_timeout(2000)
        if not _click_first(
            page,
            [
                "button[aria-label*='Add skill' i]",
                "button:has-text('Add skill')",
                "button[aria-label*='plus' i]",
            ],
        ):
            failed.append(skill)
            continue
        page.wait_for_timeout(1200)
        try:
            field = page.locator("input[name='name'], input[id*='skill' i]").first
            field.wait_for(state="visible", timeout=5000)
            field.fill(skill)
            page.wait_for_timeout(500)
            if _click_first(page, ["button:has-text('Save')"]):
                added.append(skill)
            else:
                failed.append(skill)
            page.wait_for_timeout(1000)
        except Exception:
            failed.append(skill)
    parts = []
    if added:
        parts.append(f"skills: added {len(added)} ({', '.join(added[:5])}{'…' if len(added) > 5 else ''})")
    if failed:
        parts.append(f"skills: {len(failed)} could not be added")
    return "; ".join(parts) if parts else "skills: nothing to add"


def _open_details_page(page, slug: str, label: str) -> str:
    """Open the edit page for sections we prepare but don't fully automate."""
    page.goto(f"https://www.linkedin.com/in/me/details/{slug}/", wait_until="domcontentloaded", timeout=40_000)
    return f"{label}: edit page opened — review and paste the prepared text"


def _apply_to_linkedin(data: dict, sections: list[str], player=None) -> str:
    results = []
    headless = False  # headed so first-run login / checkpoints are possible
    pw, context, page = _launch_browser(headless)
    try:
        if not _is_logged_in(page):
            page.goto("https://www.linkedin.com/login", timeout=40_000)
            if player:
                player.write_log("SYS: Waiting for LinkedIn login in the browser window…")
            if not _wait_for_manual_login(page, player):
                return (
                    "I opened LinkedIn but couldn't confirm you logged in within four minutes. "
                    "Log in manually in that window and ask me again — the session will be remembered."
                )

        for section in sections:
            try:
                if section == "headline":
                    if data.get("headline"):
                        results.append(_update_headline(page, data["headline"]))
                elif section == "about":
                    if data.get("about"):
                        results.append(_update_about(page, data["about"]))
                elif section == "skills":
                    if data.get("skills"):
                        results.append(_add_skills(page, data["skills"]))
                elif section == "experience":
                    results.append(_open_details_page(page, "experience", "experience"))
                elif section == "education":
                    results.append(_open_details_page(page, "education", "education"))
            except Exception as e:
                results.append(f"{section}: failed ({str(e)[:80]})")
    finally:
        try:
            context.close()
            pw.stop()
        except Exception:
            pass
    return results


# ── Formatting helpers ───────────────────────────────────────────────────────


def _format_preview(data: dict, sections: list[str]) -> str:
    lines = ["Here's the LinkedIn content I prepared:", ""]
    if "headline" in sections and data.get("headline"):
        lines += ["HEADLINE", data["headline"], ""]
    if "about" in sections and data.get("about"):
        lines += ["ABOUT", data["about"], ""]
    if "experience" in sections and data.get("experience"):
        lines.append("EXPERIENCE")
        for e in data["experience"]:
            lines.append(f"- {e.get('title','')} at {e.get('company','')} ({e.get('dates','')}): {e.get('description','')}")
        lines.append("")
    if "education" in sections and data.get("education"):
        lines.append("EDUCATION")
        for e in data["education"]:
            lines.append(f"- {e.get('degree','')}, {e.get('school','')} ({e.get('dates','')})")
        lines.append("")
    if "skills" in sections and data.get("skills"):
        lines += ["SKILLS", ", ".join(data["skills"]), ""]
    return "\n".join(lines).strip()


# ── Tool entry point ─────────────────────────────────────────────────────────


def linkedin_update(parameters: dict | None = None, response=None, player=None, speak=None) -> str:
    parameters = parameters or {}
    preview_only = bool(parameters.get("preview_only"))
    sections_raw = parameters.get("sections") or VALID_SECTIONS
    if isinstance(sections_raw, str):
        sections_raw = [s.strip() for s in sections_raw.split(",") if s.strip()]
    sections = [s for s in sections_raw if s in VALID_SECTIONS] or VALID_SECTIONS
    explicit_path = (parameters.get("resume_path") or "").strip() or None

    try:
        if player:
            player.write_log("SYS: LinkedIn updater started.")

        source: Path | None = None
        data: dict | None = None

        if explicit_path is None:
            cached = _load_cache()
            fresh_enough = cached and cached.get("_meta", {}).get("source_file")
            if fresh_enough and not any(
                s not in cached for s in ("headline", "about", "experience", "education", "skills")
            ):
                data = cached
                if player:
                    player.write_log(f"SYS: Using previously parsed resume: {cached['_meta']['source_file']}")

        if data is None:
            source = _find_resume(explicit_path)
            if player:
                player.write_log(f"SYS: Reading resume: {source.name}")
            text = _extract_text(source)
            if len(text.strip()) < 60:
                raise ValueError("The file doesn't contain readable text. Is it a scanned image?")
            if player:
                player.write_log("SYS: Analyzing resume with AI and writing LinkedIn copy…")
            data = _analyze_resume(text, sections)
            _save_cache(data, source)

        if preview_only:
            preview = _format_preview(data, sections)
            if player and hasattr(player, "show_content"):
                player.show_content("LINKEDIN PREVIEW", preview)
            return "Preview ready — the generated LinkedIn content is on screen."

        updates = _apply_to_linkedin(data, sections, player)
        ok = [u for u in updates if ": updated" in u or ": added" in u]
        problems = [u for u in updates if u not in ok]
        summary_parts = []
        if ok:
            summary_parts.append("Updated " + ", ".join(u.split(":")[0] for u in ok))
        if problems:
            summary_parts.append("Needs your attention: " + "; ".join(problems))
        return ". ".join(summary_parts) + "." if summary_parts else "Nothing was changed."

    except FileNotFoundError as e:
        return str(e)
    except Exception as e:
        return f"LinkedIn update failed: {e}"


if __name__ == "__main__":
    print(linkedin_update({"preview_only": True}))
