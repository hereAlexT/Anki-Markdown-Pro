# Markdown Pro

> Write Anki cards in pure Markdown — beautifully rendered on every device.

Stop fighting Anki's rich-text editor. Write your flashcards the way you write everything else — in Markdown — and get gorgeous, code-ready cards with full [syntax highlighting](docs.md#code-blocks) on desktop, AnkiDroid, AnkiMobile, and AnkiWeb.

**Download** 👉 [AnkiWeb `2081475824`](https://ankiweb.net/shared/info/2081475824?cb=1785244767408)

<img src="./imgs/screenshot.jpg" alt="Screenshot of Markdown Pro" />

> [!NOTE]
> Requires [Anki](https://apps.ankiweb.net/) 25.x or later. Go to `Tools → Add-ons → Get Add-ons` and enter [`2081475824`](https://ankiweb.net/shared/info/2081475824), or install from a release `.ankiaddon` file.
> See the [documentation](docs.md) for all supported features.

## Highlights

- ![NEW ](imgs/badge-new.svg) **Paste & drag media** — images, audio, and video go straight into the plain-text editor: screenshots, web images, and files land in your collection with the reference inserted at the cursor
- ![NEW](imgs/badge-new.svg) **All card types, fully supported**:
  - `Markdown Pro` — basic front/back
  - `Markdown Pro Cloze` — cloze deletions, with hints and blur mode
  - `Markdown Pro (and reversed)` — two cards per note
  - `Markdown Pro (optional reversed)` — reverse card on demand
  - `Markdown Pro (type in the answer)` — Anki's native green/red answer comparison
- ![NEW](imgs/badge-new.svg) **Plays nice with other add-ons** — HyperTTS / AwesomeTTS template edits survive updates; `[sound:]` audio and native replay buttons render correctly
- ![NEW](imgs/badge-new.svg) **Correct audio behavior** — question audio plays on the front, answer audio on the back
- ![NEW](imgs/badge-new.svg) **Line breaks that just work** — one newline in the editor is one line break on the card
- **Syntax highlighting & code annotations** — 300+ languages, 60+ themes, powered by [Shiki](https://shiki.style); line/word highlighting, focus mode, and error/warning markers
- **Full Markdown** — bold, italic, lists, blockquotes, tables, images, GitHub-style alerts, and more
- **Clean card design** — polished light/dark styling that matches Anki's native UI
- **Settings panel** — pick languages and themes dynamically
- **Cross-platform** — desktop, AnkiDroid, AnkiMobile, and AnkiWeb
- **[AI agent skill](#ai-agent-skill)** — let AI agents write markdown flashcards via [AnkiConnect](https://foosoft.net/projects/anki-connect/)

See [docs.md](docs.md) for full usage details on all of the above.

## Usage

After installing the add-on:

1. **Create a new note** using the **Markdown Pro** note type (Add → Note Type dropdown → Markdown Pro)
2. **Write your question** in the Front field using markdown
3. **Write your answer** in the Back field using markdown
4. The markdown will be automatically rendered with syntax highlighting when you review the card

> [!NOTE]
> See the [documentation](docs.md) for all supported markdown features including code blocks, line highlighting, alerts, and more.

## AI Agent Skill

Markdown is a perfect format for AI-generated content, and this add-on leans into that. It ships with a companion skill that lets AI coding agents (Claude Code, Codex, etc.) create and manage markdown flashcards directly from your editor via [AnkiConnect](https://foosoft.net/projects/anki-connect/). The add-on renders the markdown, the skill creates it.

**Prerequisites:** Anki desktop running with [AnkiConnect](https://foosoft.net/projects/anki-connect/) installed.

Install:

```bash
npx skills add hereAlexTeng/markdown-pro -s anki
```

## Settings

Open the settings panel from `Tools → Add-ons → Markdown Pro → Config`.

- **Languages** — pick which languages are available for syntax highlighting. New languages are downloaded on save. Use the filter and "Selected only" toggle to manage your list.
- **Theme** — choose separate Shiki themes for light and dark mode.
- **UI** — toggle cardless mode for a borderless card design.

## Development

See [development.md](development.md) for build, test, and release instructions.

## Fork Notice

This project is a fork of [terkelg/anki-markdown](https://github.com/terkelg/anki-markdown) by [Terkel Gjervig](https://github.com/terkelg), used under the [MIT License](license). All credit for the original architecture, renderer, and syntax-highlighting engine goes to the upstream project — go star it.
