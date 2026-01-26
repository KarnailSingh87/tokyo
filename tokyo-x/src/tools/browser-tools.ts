function decodeEntities(s: string): string {
  return s
    .replace(/&/g, "&")
    .replace(/</g, "<")
    .replace(/>/g, ">")
    .replace(/"/g, '"')
    .replace(/'/g, "'")
    .replace(/'/g, "'");
}

function stripTags(s: string): string {
  return s.replace(/<[^>]+>/g, "").trim();
}

function extractDuckDuckGoUrl(href: string): string {
  const m = href.match(/uddg=([^&]+)/);
  return m ? decodeURIComponent(m[1]) : href;
}

export function createBrowserTools() {
  return {
    "browser.open": async (args: Record<string, unknown>) => {
      const urlStr = String(args.url ?? "");
      let url: URL;
      try {
        url = new URL(urlStr);
      } catch {
        throw new Error("invalid url");
      }
      if (url.protocol !== "http:" && url.protocol !== "https:") throw new Error("only http/https allowed");
      const res = await fetch(url, {
        method: "GET",
        redirect: "follow",
        signal: AbortSignal.timeout(15_000),
        headers: { "user-agent": "TokyoX/0.1 (+local orchestrator)" },
      });
      const html = (await res.text()).slice(0, 200_000);
      const titleMatch = html.match(/<title[^>]*>([\s\S]*?)<\/title>/i);
      return {
        url: res.url || urlStr,
        status: res.status,
        title: titleMatch ? decodeEntities(stripTags(titleMatch[1])).slice(0, 200) : "",
        bytes: html.length,
      };
    },
    "browser.search": async (args: Record<string, unknown>) => {
      const q = String(args.query ?? "").slice(0, 300);
      if (!q) throw new Error("query required");
      const res = await fetch(`https://html.duckduckgo.com/html/?q=${encodeURIComponent(q)}`, {
        signal: AbortSignal.timeout(15_000),
        headers: { "user-agent": "TokyoX/0.1" },
      });
      const html = await res.text();
      const results: Array<{ title: string; url: string }> = [];
      const re = /<a[^>]*class="result__a"[^>]*href="([^"]+)"[^>]*>([\s\S]*?)<\/a>/g;
      for (const m of html.matchAll(re)) {
        const title = decodeEntities(stripTags(m[2])).slice(0, 180);
        const url = extractDuckDuckGoUrl(m[1]);
        if (title && url) results.push({ title, url });
        if (results.length >= 5) break;
      }
      return { query: q, results };
    },
    "browser.act": async () => {
      throw new Error("browser.act requires an automation driver (planned phase 8+ scaffold)");
    },
  };
}