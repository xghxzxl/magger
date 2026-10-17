"""Two-stage editorial review for Magger."""
from __future__ import annotations
import argparse, html, json, os, re, urllib.request
from datetime import datetime, timedelta, timezone
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urlsplit
import yaml
from magger.cli import _load_state, _rss_summary
from magger.feeds import article_id, canonical_url, fetch_recent
from magger.magazine import build_epub
from magger.delivery import send_to_kindle

def load_yaml(path):
    with open(path, encoding="utf-8") as f: value = yaml.safe_load(f) or {}
    if not isinstance(value, dict): raise ValueError(f"Expected YAML mapping: {path}")
    return value

def report(text):
    print(text)
    target=os.environ.get("GITHUB_STEP_SUMMARY")
    if target:
        with open(target,"a",encoding="utf-8") as f: f.write(text+"\n")

def review(args):
    settings=load_yaml(args.editorial).get("magazine",{})
    state=_load_state(Path(args.state))["seen"]
    candidates=[a for a in fetch_recent(load_yaml(args.feeds).get("feeds",[]),int(settings.get("lookback_days",7))) if a["id"] not in state][:int(settings.get("max_articles",12))]
    for a in candidates: a["synopsis"]=_rss_summary(a.get("description",""),a["title"],int(settings.get("summary_max_words",100)))
    manifest={"created_at":datetime.now(timezone.utc).isoformat(),"settings":settings,"candidates":candidates}
    Path(args.output).parent.mkdir(parents=True,exist_ok=True)
    Path(args.output).write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    lines=["# Magger — editorial approval","","Found **%d** unseen RSS candidates in the last **%s days**."%(len(candidates),settings.get("lookback_days",7)),"","Nothing is sent automatically. In a separate **Publish approved edition** run, enter candidate numbers in the include input (comma-separated, e.g. 1,3,4) and/or paste URLs into extra_urls (one per line).",""]
    for i,a in enumerate(candidates,1): lines += [f"## {i}. {a['title']}",f"- **Source:** {a.get('feed','RSS')}",f"- **Date:** {a.get('published','')[:10]}",f"- **Link:** {a['url']}",f"- **RSS synopsis:** {a['synopsis']}",""]
    if not candidates: lines += ["No new RSS candidates. You can still add manual URLs when publishing."]
    report("\n".join(lines)); return 0

class MetaParser(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True); self.in_title=False; self.title=[]; self.meta={}
    def handle_starttag(self,tag,attrs):
        attrs=dict(attrs)
        if tag.lower()=="title": self.in_title=True
        if tag.lower()=="meta":
            key=(attrs.get("property") or attrs.get("name") or "").lower()
            if key and attrs.get("content"): self.meta.setdefault(key,attrs["content"])
    def handle_endtag(self,tag):
        if tag.lower()=="title": self.in_title=False
    def handle_data(self,data):
        if self.in_title and data.strip(): self.title.append(data.strip())

class ArticleParser(MetaParser):
    """Extract readable paragraphs, preferring article/main content."""
    SKIP = {"script", "style", "nav", "footer", "header", "aside", "form", "noscript", "svg"}
    def __init__(self):
        super().__init__()
        self.stack = []
        self.paragraph = []
        self.paragraphs = []
        self.main_paragraphs = []
        self.main_depth = 0
        self.in_paragraph = False

    def handle_starttag(self, tag, attrs):
        tag = tag.lower()
        attrs_dict = dict(attrs)
        self.stack.append(tag)
        if tag in ("main", "article"):
            self.main_depth += 1
        if tag == "title":
            self.in_title = True
        if tag == "meta":
            key = (attrs_dict.get("property") or attrs_dict.get("name") or "").lower()
            if key and attrs_dict.get("content"):
                self.meta.setdefault(key, attrs_dict["content"])
        if tag == "p":
            self.in_paragraph = True
            self.paragraph = []

    def handle_endtag(self, tag):
        tag = tag.lower()
        if tag == "title":
            self.in_title = False
        if tag == "p" and self.in_paragraph:
            text = " ".join(" ".join(self.paragraph).split())
            if len(text) > 25:
                self.paragraphs.append(text)
                if self.main_depth:
                    self.main_paragraphs.append(text)
            self.paragraph = []
            self.in_paragraph = False
        if tag in ("main", "article") and self.main_depth:
            self.main_depth -= 1
        if tag in self.stack:
            # HTML can be malformed; unwind through the matching open element.
            pos = len(self.stack) - 1 - self.stack[::-1].index(tag)
            del self.stack[pos:]

    def handle_data(self, data):
        if self.in_title and data.strip():
            self.title.append(data.strip())
        if self.in_paragraph and not any(tag in self.SKIP for tag in self.stack):
            value = data.strip()
            if value:
                self.paragraph.append(value)


def fetch_article_content(article):
    """Fetch article HTML and attach readable text, falling back to the RSS synopsis."""
    url = article.get("url", "")
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (compatible; Magger/0.1; +https://github.com/xghxzxl/magger)"})
        with urllib.request.urlopen(req, timeout=20) as response:
            content_type = response.headers.get("Content-Type", "").lower()
            if "html" not in content_type and content_type:
                raise ValueError("URL did not return HTML")
            parser = ArticleParser()
            parser.feed(response.read(3_000_000).decode("utf-8", errors="replace"))
        paragraphs = parser.main_paragraphs if sum(map(len, parser.main_paragraphs)) >= 400 else parser.paragraphs
        # De-duplicate repeated text often found in page templates.
        unique = []
        seen_paragraphs = set()
        for paragraph in paragraphs:
            key = paragraph.casefold()
            if key not in seen_paragraphs:
                unique.append(paragraph)
                seen_paragraphs.add(key)
        full_text = "\\n\\n".join(unique)[:30000].strip()
        if full_text:
            article["full_text"] = full_text
            if parser.meta.get("og:title") or parser.title:
                article["title"] = html.unescape((parser.meta.get("og:title") or " ".join(parser.title)).strip())
            return
    except Exception as exc:
        print(f"Warning: article text extraction failed for {url}: {exc}")
    fallback = article.get("description") or article.get("synopsis") or article.get("editorial_summary") or ""
    article["full_text"] = _rss_summary(fallback, article.get("title", "Article"), 1000)
    article["content_fallback"] = True


def manual_article(raw):
    url=canonical_url(raw.strip())
    if urlsplit(url).scheme not in ("http","https") or not urlsplit(url).netloc: raise ValueError("Invalid http(s) URL: "+raw)
    title=url; description=""
    try:
        req=urllib.request.Request(url,headers={"User-Agent":"Magger/0.1"})
        with urllib.request.urlopen(req,timeout=15) as response:
            final=canonical_url(response.geturl())
            if urlsplit(final).scheme in ("http","https"): url=final
            if "html" in response.headers.get("Content-Type","").lower():
                parser=MetaParser(); parser.feed(response.read(1000000).decode("utf-8",errors="replace"))
                title=(parser.meta.get("og:title") or parser.meta.get("twitter:title") or " ".join(parser.title) or url).strip()
                description=(parser.meta.get("og:description") or parser.meta.get("description") or parser.meta.get("twitter:description") or "").strip()
    except Exception as exc: print(f"Warning: metadata fetch failed for {url}: {exc}; using URL as title.")
    return {"id":article_id(url),"title":html.unescape(title),"url":url,"published":datetime.now(timezone.utc).isoformat(),"feed":"Manually added","description":description[:12000],"synopsis":_rss_summary(description,title,100),"topic":"Manually added","rationale":"Manually supplied and explicitly approved by the editor."}

def publish(args):
    manifest=json.loads(Path(args.draft).read_text(encoding="utf-8"))
    settings=load_yaml(args.editorial).get("magazine",manifest.get("settings",{}))
    state_path=Path(args.state); state=_load_state(state_path); seen=state["seen"]; candidates=manifest.get("candidates",[])
    indices=set()
    for part in args.include.split(","):
        part=part.strip()
        if not part: continue
        if not part.isdigit() or not 1<=int(part)<=len(candidates): raise ValueError("Invalid candidate number %r; valid range 1-%d."%(part,len(candidates)))
        indices.add(int(part))
    selected=[]
    for i in sorted(indices):
        a=dict(candidates[i-1]); a["topic"]=a.get("feed") or "RSS"; a["rationale"]="Explicitly approved by the editor."
        a["editorial_summary"]=a.get("synopsis") or _rss_summary(a.get("description",""),a["title"],int(settings.get("summary_max_words",100))); selected.append(a)
    for raw in args.extra_urls.splitlines():
        raw=raw.strip()
        if raw and not raw.startswith("#"):
            a=manual_article(raw)
            if a["id"] not in {x["id"] for x in selected}:
                a["editorial_summary"]=a["synopsis"]; selected.append(a)
    selected=[a for a in selected if a["id"] not in seen]
    if not selected: raise ValueError("No new articles approved. Nothing was sent.")
    output=Path(args.output or ("dist/magger-"+datetime.now(timezone.utc).astimezone().strftime("%Y-%m-%d")+".epub"))
    for article in selected:
        fetch_article_content(article)
    build_epub(selected,settings,output)
    if args.no_email: report(f"Preview EPUB built with {len(selected)} approved articles; no email sent and state unchanged.")
    else:
        send_to_kindle(output); now=datetime.now(timezone.utc)
        for a in selected: seen[a["id"]]={"url":a["url"],"published":a["published"],"checked_at":now.isoformat()}
        cutoff=now-timedelta(days=max(90,int(settings.get("lookback_days",7))*12))
        state["seen"]={k:v for k,v in seen.items() if v.get("checked_at") and datetime.fromisoformat(v["checked_at"])>=cutoff}
        state_path.parent.mkdir(parents=True,exist_ok=True); state_path.write_text(json.dumps(state,indent=2,ensure_ascii=False)+"\n",encoding="utf-8")
        report(f"Published and delivered {len(selected)} approved articles to Kindle.")
    print(f"Wrote {output} ({output.stat().st_size} bytes)."); return 0

def main():
    p=argparse.ArgumentParser(description="Magger editorial approval workflow"); sub=p.add_subparsers(dest="command",required=True)
    r=sub.add_parser("review"); r.add_argument("--feeds",default="config/feeds.yml"); r.add_argument("--editorial",default="config/editorial.yml"); r.add_argument("--state",default="data/seen.json"); r.add_argument("--output",default="draft/manifest.json")
    q=sub.add_parser("publish"); q.add_argument("--draft",default="draft/manifest.json"); q.add_argument("--include",default=""); q.add_argument("--extra-urls",default=""); q.add_argument("--editorial",default="config/editorial.yml"); q.add_argument("--state",default="data/seen.json"); q.add_argument("--output"); q.add_argument("--no-email",action="store_true")
    a=p.parse_args(); raise SystemExit(review(a) if a.command=="review" else publish(a))
if __name__=="__main__": main()
