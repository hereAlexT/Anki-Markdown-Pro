import { beforeAll, describe, expect, test } from "bun:test";
import { Window } from "happy-dom";

beforeAll(() => {
  const window = new Window();
  (globalThis as any).document = window.document;
});

import { sanitizeInline, sanitizeBlock, safeUrl } from "../src/sanitize";
import { extractAv, restoreAv } from "../src/av";

describe("sanitizeInline", () => {
  test("keeps allowed tags and attributes", () => {
    expect(sanitizeInline('<img src="x.png" alt="pic">')).toBe('<img src="x.png" alt="pic">');
    expect(sanitizeInline("</b>")).toBe("</b>");
    expect(sanitizeInline("<kbd>")).toBe("<kbd>");
  });

  test("strips event handlers and unknown attributes", () => {
    expect(sanitizeInline('<img src="x.png" onerror="alert(1)">')).toBe('<img src="x.png">');
    expect(sanitizeInline('<a href="https://a.example" target="_blank">')).toBe('<a href="https://a.example">');
  });

  test("blocks javascript: URLs", () => {
    expect(sanitizeInline("<a href=\"javascript:alert(1)\">")).toBe("<a>");
    expect(sanitizeInline('<a href="JaVaScRiPt:alert(1)">')).toBe("<a>");
    expect(sanitizeInline('<a href="java\nscript:alert(1)">')).toBe("<a>");
  });

  test("data: URLs only for images", () => {
    expect(sanitizeInline('<img src="data:image/png;base64,AAA">')).toBe('<img src="data:image/png;base64,AAA">');
    expect(sanitizeInline('<a href="data:text/html,x">')).toBe("<a>");
  });

  test("drops disallowed tags", () => {
    expect(sanitizeInline("<script>")).toBe("");
    expect(sanitizeInline("<iframe>")).toBe("");
    expect(sanitizeInline("<div>")).toBe("");
  });

  test("allows audio/video/source", () => {
    expect(sanitizeInline('<audio src="a.mp3" controls>')).toBe('<audio src="a.mp3" controls>');
    expect(sanitizeInline('<video src="v.mp4" controls>')).toBe('<video src="v.mp4" controls>');
    expect(sanitizeInline('<source src="v.webm" type="video/webm">')).toBe('<source src="v.webm" type="video/webm">');
  });
});

describe("sanitizeBlock", () => {
  test("drops script elements entirely", () => {
    expect(sanitizeBlock("<script>alert(1)</script>")).toBe("");
    expect(sanitizeBlock("a<script>x</script>b")).toBe("ab");
  });

  test("unwraps unknown elements but keeps children", () => {
    expect(sanitizeBlock("<div><b>x</b></div>")).toBe("<b>x</b>");
    expect(sanitizeBlock("<p>hello <em>world</em></p>")).toBe("hello <em>world</em>");
  });

  test("filters attributes on nested elements", () => {
    expect(sanitizeBlock('<div><img src="x.png" onload="evil()"></div>')).toBe('<img src="x.png">');
  });

  test("removes comments", () => {
    expect(sanitizeBlock("a<!-- hidden -->b")).toBe("ab");
  });
});

describe("safeUrl", () => {
  test("relative and http(s) allowed", () => {
    expect(safeUrl("x.png", "img")).toBe(true);
    expect(safeUrl("https://example.com/a.png", "img")).toBe(true);
  });

  test("javascript blocked", () => {
    expect(safeUrl("javascript:x", "a")).toBe(false);
    expect(safeUrl(" java\tscript:x", "a")).toBe(false);
  });
});

describe("av passthrough", () => {
  test("extracts and restores raw [sound:] as audio element", () => {
    const { text, items } = extractAv("hear this: [sound:clip.mp3]");
    expect(text).toBe("hear this: MDPROAV0X");
    expect(items).toEqual(["[sound:clip.mp3]"]);
    expect(restoreAv("<p>hear this: MDPROAV0X</p>", items)).toBe(
      '<p>hear this: <audio controls src="clip.mp3"></audio></p>',
    );
  });

  test("video extensions render a video element", () => {
    const { items } = extractAv("[sound:demo.mp4]");
    expect(restoreAv("MDPROAV0X", items)).toBe('<video controls src="demo.mp4"></video>');
  });

  test("keeps anki play markers untouched", () => {
    const { text, items } = extractAv("[anki:play:q:0]");
    expect(restoreAv(text, items)).toBe("[anki:play:q:0]");
  });

  test("keeps valid replay buttons including their play onclick", () => {
    const anchor = "<a class=\"replay-button soundLink\" href=\"#\" onclick=\"pycmd('play:q:0'); return false;\"><svg viewBox=\"0 0 64 64\"></svg></a>";
    const { text, items } = extractAv(`x ${anchor} y`);
    expect(text).toBe("x MDPROAV0X y");
    const restored = restoreAv("x MDPROAV0X y", items);
    expect(restored).toContain("replay-button");
    expect(restored).toContain("pycmd('play:q:0')");
    expect(restored).toContain("<svg");
  });

  test("strips forged handlers on fake replay buttons", () => {
    const forged = '<a class="replay-button" onclick="evil()" onmouseover="evil()">x</a>';
    const { text, items } = extractAv(forged);
    const restored = restoreAv(text, items);
    expect(restored).not.toContain("evil");
    expect(restored).toContain("replay-button");
  });

  test("multiple items restore in order", () => {
    const { text, items } = extractAv("[sound:a.mp3] and [sound:b.mp3]");
    expect(text).toBe("MDPROAV0X and MDPROAV1X");
    const restored = restoreAv(text, items);
    expect(restored).toContain("a.mp3");
    expect(restored).toContain("b.mp3");
  });
});
