/**
 * knowly-sync extension — reference implementation
 *
 * Usage:
 *   pi --knowly              Upload the latest session to knowly and exit
 *   pi --knowly "标题"        Same, with a custom title (also used in the filename)
 *
 * Uploads the session as a Markdown transcript to the knowly upload API. The
 * .md upload triggers the server-side AI sync -> archive -> index -> publish
 * pipeline.
 *
 * Demonstrates:
 *   - CLI flag registration with an optional value (`registerFlag` + `getFlag`)
 *   - The `session_start` event for one-shot startup actions
 *   - Parsing a session JSONL file and rebuilding the main line via `parentId`
 *     (event-sourcing replay; see session-manager.ts `buildSessionPath`)
 *   - Streaming a multipart/form-data upload with fetch + FormData
 *   - The one-shot exit pattern: `ctx.shutdown()` is a no-op before the
 *     interactive mode binds its handler, so exit via `process.exit()` directly.
 *
 * Credentials come from environment variables (never hardcode secrets in an
 * example): KNOWLY_URL (defaults to the knowly upload endpoint),
 * KNOWLY_USER (default: "knowly"), KNOWLY_PASS (required).
 */

import { readdirSync, readFileSync, statSync } from "node:fs";
import { join } from "node:path";
import type { ExtensionAPI, ExtensionContext } from "@earendil-works/pi-coding-agent";

const KNOWLY_URL = process.env.KNOWLY_URL ?? "https://upload.want.biz/api/upload";
const KNOWLY_USER = process.env.KNOWLY_USER ?? "knowly";
const KNOWLY_PASS = process.env.KNOWLY_PASS;

/** Hard cap on the generated Markdown size; keeps documents sane. */
const MAX_TOTAL_BYTES = 4 * 1024 * 1024;

/** Minimal message shape parsed from session JSONL (sessions may be hand-edited). */
interface SessionMessage {
	role?: string;
	content?: Array<{ type?: string; text?: string }> | null;
}

interface SessionEntry {
	type: string;
	id: string;
	parentId: string | null;
	timestamp: string;
	cwd?: string;
	provider?: string;
	modelId?: string;
	thinkingLevel?: string;
	message?: SessionMessage;
}

interface SessionFile {
	path: string;
	entries: SessionEntry[];
}

export function loadSessionFile(filePath: string): SessionFile {
	const entries: SessionEntry[] = [];
	for (const line of readFileSync(filePath, "utf8").split("\n")) {
		if (!line.trim()) continue;
		try {
			entries.push(JSON.parse(line) as SessionEntry);
		} catch {
			// Skip malformed lines (sessions may be hand-edited).
		}
	}
	return { path: filePath, entries };
}

/** Follow the parentId chain from the last entry to the root. */
export function buildSessionPath(entries: SessionEntry[]): SessionEntry[] {
	const byId = new Map<string, SessionEntry>();
	for (const entry of entries) byId.set(entry.id, entry);
	const leaf = entries[entries.length - 1];
	if (!leaf) return [];
	const path: SessionEntry[] = [];
	let current: SessionEntry | undefined = leaf;
	while (current) {
		path.push(current);
		current = current.parentId ? byId.get(current.parentId) : undefined;
	}
	return path.reverse();
}

function textBlocks(message: SessionMessage): string[] {
	if (!Array.isArray(message.content)) return [];
	return message.content
		.filter((block) => block.type === "text" && typeof block.text === "string")
		.map((block) => block.text as string);
}

function messageText(message: SessionMessage, truncate: number): string {
	const text = textBlocks(message).join("\n\n");
	if (text.length > truncate) {
		return `${text.slice(0, truncate)}\n\n[输出已截断，原文 ${text.length} 字符]`;
	}
	return text;
}

function slugify(text: string): string {
	const slug = text.replace(/[^\p{L}\p{N}]+/gu, "-").replace(/^-+|-+$/g, "");
	return slug || "session";
}

export function buildMarkdown(file: SessionFile, customTitle?: string): { title: string; markdown: string } {
	const path = buildSessionPath(file.entries);
	const header =
		path.find((entry) => entry.type === "session") ?? file.entries.find((entry) => entry.type === "session");
	const date = (header?.timestamp ?? new Date().toISOString()).slice(0, 10);
	const title = customTitle || `Pi 会话记录 ${date}`;

	const lines: string[] = [`# ${title}`, ""];
	lines.push(
		`- **会话 ID**: ${header?.id ?? "未知"}`,
		`- **开始时间**: ${header?.timestamp ?? "未知"}`,
		`- **工作目录**: ${header?.cwd ?? "未知"}`,
		`- **条目数**: ${file.entries.length}`,
		"",
	);

	const TOOL_RESULT_LIMIT = 1500;
	let budget = MAX_TOTAL_BYTES;
	const consume = (chars: number): boolean => {
		budget -= chars;
		return budget >= 0;
	};

	for (const entry of path) {
		if (entry.type === "session") continue;
		if (entry.type === "model_change") {
			lines.push(`> 模型切换: ${entry.provider}/${entry.modelId}`);
			continue;
		}
		if (entry.type === "thinking_level_change") {
			lines.push(`> 思考级别: ${entry.thinkingLevel}`);
			continue;
		}
		if (entry.type !== "message" || !entry.message) continue;

		const message = entry.message;
		switch (message.role) {
			case "user": {
				const text = messageText(message, 4000);
				if (!consume(text.length)) return { title, markdown: lines.join("\n") };
				lines.push(`## 👤 用户`, "", text, "");
				break;
			}
			case "assistant": {
				const text = messageText(message, 10000);
				if (!consume(text.length)) return { title, markdown: lines.join("\n") };
				lines.push(`## 🤖 Assistant`, "", text, "");
				break;
			}
			case "toolResult": {
				const text = messageText(message, TOOL_RESULT_LIMIT);
				if (!consume(text.length + 100)) {
					lines.push(
						`### 🛠 工具结果`,
						"",
						`_其余工具输出已省略（超出 ${MAX_TOTAL_BYTES / 1024 / 1024}MB 预算）_`,
						"",
					);
					return { title, markdown: lines.join("\n") };
				}
				lines.push(`### 🛠 工具结果`, "", "```", text, "```", "");
				break;
			}
			default:
				break;
		}
	}

	return { title, markdown: lines.join("\n") };
}

/** Pick the latest session to upload: prefer a non-empty current session, else newest file. */
export function pickLatestSession(ctx: ExtensionContext): SessionFile | undefined {
	const sessionDir = ctx.sessionManager.getSessionDir();
	const currentEntries = ctx.sessionManager.getEntries() as SessionEntry[];
	const currentHasMessages = currentEntries.some((entry) => entry.type === "message");
	const currentSessionFile = ctx.sessionManager.getSessionFile();
	if (currentHasMessages && currentSessionFile) {
		return { path: currentSessionFile, entries: currentEntries };
	}

	let latest: SessionFile | undefined;
	let files: string[] = [];
	try {
		files = readdirSync(sessionDir).filter((name) => name.endsWith(".jsonl"));
	} catch {
		return undefined;
	}
	for (const name of files) {
		const file = loadSessionFile(join(sessionDir, name));
		if (!file.entries.some((entry) => entry.type === "message")) continue;
		if (!latest || statSync(file.path).mtimeMs > statSync(latest.path).mtimeMs) {
			latest = file;
		}
	}
	return latest;
}

export function sessionFileMarkdownName(session: SessionFile, customTitle?: string): string {
	const header = session.entries.find((entry) => entry.type === "session");
	const date = (header?.timestamp ?? new Date().toISOString()).slice(0, 10);
	const shortId = header?.id ? header.id.slice(0, 8) : "unknown";
	if (customTitle) {
		return `pi-${slugify(customTitle)}-${date}-${shortId}.md`;
	}
	return `pi-session-${date}-${shortId}.md`;
}

async function uploadToKnowly(markdown: string, filename: string): Promise<{ status: number; body: string }> {
	if (!KNOWLY_PASS) {
		throw new Error("KNOWLY_PASS is not set. Set KNOWLY_URL/KNOWLY_USER/KNOWLY_PASS to upload.");
	}
	const auth = `Basic ${Buffer.from(`${KNOWLY_USER}:${KNOWLY_PASS}`).toString("base64")}`;
	const form = new FormData();
	form.append("file", new Blob([markdown], { type: "text/markdown" }), filename);
	const response = await fetch(KNOWLY_URL, {
		method: "POST",
		headers: { Authorization: auth },
		body: form,
		signal: AbortSignal.timeout(120_000),
	});
	return { status: response.status, body: await response.text() };
}

function report(ctx: ExtensionContext, message: string, type: "info" | "warning" | "error"): void {
	try {
		ctx.ui.notify(message, type);
	} catch {
		// Notify is unavailable outside the TUI; fall through to console output.
	}
	if (type === "error") {
		console.error(`[knowly] ${message}`);
	} else {
		console.log(`[knowly] ${message}`);
	}
}

/**
 * Exit pi after the one-shot --knowly run.
 * ctx.shutdown() is a no-op before the interactive mode binds its handler
 * (session_start fires during runtime creation), so exit the process directly.
 * A short delay lets pending TTY output flush.
 */
function exitAfterOneShot(code: number): void {
	setTimeout(() => process.exit(code), 100);
}

export default function knowlySyncExtension(pi: ExtensionAPI) {
	// "string" so `--knowly "标题"` passes a custom title while a bare `--knowly` yields `true`.
	pi.registerFlag("knowly", {
		description: "Upload the latest session to knowly and exit. Optional value: custom title",
		type: "string",
	});

	pi.on("session_start", async (_event, ctx) => {
		const flagValue = pi.getFlag("knowly");
		if (flagValue === undefined) return;
		const customTitle = typeof flagValue === "string" ? flagValue : undefined;

		try {
			const session = pickLatestSession(ctx);
			if (!session) {
				report(ctx, "没有找到含消息的会话。", "warning");
				exitAfterOneShot(1);
				return;
			}

			const { title, markdown } = buildMarkdown(session, customTitle);
			const filename = sessionFileMarkdownName(session, customTitle);
			const result = await uploadToKnowly(markdown, filename);

			if (result.status >= 200 && result.status < 300) {
				report(ctx, `已上传会话《${title}》(${filename})`, "info");
				report(ctx, `响应: ${result.body}`, "info");
				exitAfterOneShot(0);
			} else {
				report(ctx, `上传失败 (HTTP ${result.status}): ${result.body}`, "error");
				exitAfterOneShot(1);
			}
		} catch (error) {
			report(ctx, `上传出错: ${error instanceof Error ? error.message : String(error)}`, "error");
			exitAfterOneShot(1);
		}
	});
}
