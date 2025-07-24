import json
import os
from datetime import datetime

GAP_SECONDS = 30 * 60  # 30 minutes


def load_conversations(path):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def format_time(ts):
    if ts is None:
        return 'N/A'
    if isinstance(ts, str):
        try:
            ts = float(ts)
        except ValueError:
            return "N/A"
    if ts and ts > 1e12:
        ts = ts / 1000.0
    try:
        return datetime.fromtimestamp(ts).strftime("%Y-%m-%d %H:%M:%S")
    except Exception:
        return "N/A"


def reconstruct_threads(mapping):
    """Reconstruct conversation threads using parent/child links."""

    if not mapping:
        return []

    nodes = {}
    for mid, data in mapping.items():
        node = {
            "id": mid,
            "parent": data.get("parent"),
            "children": data.get("children") or [],
        }
        msg = data.get("message") or {}
        role = msg.get("author", {}).get("role")
        parts = msg.get("content", {}).get("parts") or []
        text = "\n".join(str(p) for p in parts if p is not None)
        ts = msg.get("create_time")
        if ts is not None:
            try:
                ts = float(ts)
            except (TypeError, ValueError):
                ts = None
        node.update({"role": role, "text": text, "time": ts})
        nodes[mid] = node

    leaves = [mid for mid, n in nodes.items() if not n["children"]]
    threads = []
    for leaf in leaves:
        path = []
        seen = set()
        cur = leaf
        while cur and cur not in seen:
            seen.add(cur)
            node = nodes.get(cur)
            if not node:
                break
            if node.get("role"):
                path.append({"role": node["role"], "text": node["text"], "time": node["time"]})
            cur = node.get("parent")
        path.reverse()
        if path:
            threads.append(path)

    return threads


def split_segments(messages, gap_seconds=GAP_SECONDS):
    """Split a message list into segments on role change or long time gap."""

    if not messages:
        return []

    messages = sorted(messages, key=lambda m: m.get("time") or 0)
    segments: list[list[dict]] = []
    current: list[dict] = [messages[0]]

    for prev, cur in zip(messages, messages[1:]):
        prev_time = prev.get("time")
        cur_time = cur.get("time")

        time_gap = False
        if prev_time is not None and cur_time is not None:
            if cur_time - prev_time > gap_seconds:
                time_gap = True

        role_change = prev.get("role") != cur.get("role")

        if time_gap or role_change:
            segments.append(current)
            current = [cur]
        else:
            current.append(cur)

    if current:
        segments.append(current)

    return segments


def save_segments(title, conv_index, thread_index, segments, out_dir):
    for s_idx, seg in enumerate(segments):
        filename = os.path.join(
            out_dir,
            f"conv{conv_index:03d}_thread{thread_index:02d}_seg{s_idx:02d}.md",
        )
        with open(filename, "w", encoding="utf-8") as f:
            f.write(f"# {title} - Thread {thread_index} Segment {s_idx}\n\n")
            for msg in seg:
                timestamp = format_time(msg.get("time"))
                role = msg.get("role", "unknown")
                text = msg.get("text", "")
                f.write(f"**{timestamp} - {role}:**\n{text}\n\n")


def process_file(path, out_dir='segments'):
    os.makedirs(out_dir, exist_ok=True)
    conversations = load_conversations(path)
    for idx, conv in enumerate(conversations):
        title = conv.get("title") or f"Conversation {idx}"
        mapping = conv.get("mapping", {})
        threads = reconstruct_threads(mapping)
        for t_idx, thread in enumerate(threads):
            segments = split_segments(thread)
            save_segments(title, idx, t_idx, segments, out_dir)


if __name__ == '__main__':
    import argparse

    parser = argparse.ArgumentParser(description="Process ChatGPT conversation exports")
    parser.add_argument("json_file", help="Path to conversations.json")
    parser.add_argument("--output", default="segments", help="Output directory")
    parser.add_argument("--gap-minutes", type=float, default=30, help="Gap in minutes to start a new segment")
    args = parser.parse_args()

    globals()["GAP_SECONDS"] = int(args.gap_minutes * 60)
    process_file(args.json_file, args.output)
