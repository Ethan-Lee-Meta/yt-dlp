"""Safe subprocess adapter for a local, user-operated yt-dlp desktop UI."""
from __future__ import annotations

import hashlib
import os
import re
import shutil
import sys
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

MODES = {"single": "单个视频", "playlist": "播放列表 / 系列", "channel": "作者频道全部"}
QUALITIES = {"best": "最佳画质", "1080": "最高 1080p", "720": "最高 720p", "mp3": "仅音频 MP3"}
BROWSERS = ("不使用", "Chrome", "Edge", "Firefox")

_PROGRESS = re.compile(r"__YTDLP_PROGRESS__\s*(\d+(?:\.\d+)?)%\|([^|]*)\|(.*)")
_DONE = re.compile(r"__YTDLP_DONE__(\S+)")
_YOUTUBE_HOSTS = {
    "youtube.com", "www.youtube.com", "m.youtube.com", "music.youtube.com",
    "youtu.be", "www.youtu.be", "youtube-nocookie.com", "www.youtube-nocookie.com",
}


def check_url(url: str, mode: str) -> str:
    """Return normalized URL; reject unexpected hosts and wrong download modes."""
    value = url.strip()
    try:
        parsed = urlsplit(value)
        hostname = (parsed.hostname or "").lower().rstrip(".")
        valid_port = parsed.port in (None, 80, 443)
    except ValueError as exc:
        raise ValueError("URL 格式错误") from exc
    if (
        parsed.scheme not in ("http", "https")
        or hostname not in _YOUTUBE_HOSTS
        or parsed.username is not None
        or parsed.password is not None
        or not valid_port
    ):
        raise ValueError("请提供有效的 YouTube HTTPS/HTTP 链接")
    if mode not in MODES:
        raise ValueError("未知下载模式")

    path = parsed.path.lower()
    query = parse_qs(parsed.query)
    video = hostname.endswith("youtu.be") or (
        path.startswith(("/watch", "/shorts/", "/live/", "/embed/")) and
        (path != "/watch" or bool(query.get("v")))
    )
    playlist = path.startswith("/playlist") and bool(query.get("list"))
    playlist = playlist or (video and bool(query.get("list")))
    channel = (
        path.startswith(("/@", "/channel/", "/user/", "/c/"))
        or path.startswith("/feed/")
    )
    if mode == "single" and not video:
        raise ValueError("单个视频模式需要视频链接（watch、youtu.be、shorts 等）")
    if mode == "playlist" and not playlist:
        raise ValueError("播放列表模式需要含 list= 的播放列表链接")
    if mode == "channel" and not channel:
        raise ValueError("频道模式需要作者主页链接（/@作者 或 /channel/...）")
    return value


def check_proxy(proxy: str) -> str:
    value = proxy.strip()
    if not value:
        return ""
    try:
        parsed = urlsplit(value)
        valid_port = parsed.port is not None and 0 < parsed.port <= 65535
    except ValueError as exc:
        raise ValueError("代理地址格式错误") from exc
    if (
        parsed.scheme not in ("http", "https", "socks4", "socks5", "socks5h")
        or not parsed.hostname or not valid_port or parsed.username or parsed.password
    ):
        raise ValueError("代理格式示例：http://127.0.0.1:7890（不接受内嵌账号密码）")
    return value


def engine_command(custom_path: str = "") -> list[str]:
    """Prefer latest external yt-dlp over the possibly stale repo checkout."""
    chosen = custom_path.strip().strip('"')
    if chosen:
        target = Path(chosen).expanduser()
        if not target.is_file():
            raise ValueError("指定的 yt-dlp 可执行文件不存在")
        return [str(target)]

    env_binary = os.environ.get("YT_DLP_BINARY", "").strip().strip('"')
    if env_binary and Path(env_binary).is_file():
        return [env_binary]
    found = shutil.which("yt-dlp")
    if found:
        return [found]
    if os.name == "nt":
        known = [
            Path("D:/Program Files/yt-dlp/yt-dlp.exe"),
            Path(os.environ.get("LOCALAPPDATA", "")) / "Microsoft/WinGet/Links/yt-dlp.exe",
        ]
        for candidate in known:
            if candidate.is_file():
                return [str(candidate)]
    # Repository source or an installed Python package may supply this module.
    return [sys.executable, "-m", "yt_dlp"]


def build_command(
    engine: list[str], url: str, mode: str, folder: Path,
    quality: str = "best", subtitles: bool = False,
    browser: str = "不使用", proxy: str = "",
) -> list[str]:
    url = check_url(url, mode)
    if quality not in QUALITIES:
        raise ValueError("未知画质选项")
    if browser not in BROWSERS:
        raise ValueError("未知浏览器选项")
    proxy = check_proxy(proxy)
    folder = Path(folder).expanduser().resolve()
    folder.mkdir(parents=True, exist_ok=True)
    archive_folder = folder / ".yt-dlp-archives"
    archive_folder.mkdir(exist_ok=True)
    digest = hashlib.sha256(url.encode("utf-8")).hexdigest()[:16]
    archive = archive_folder / f"{mode}-{digest}.txt"

    patterns = {
        "single": "%(title).160B [%(id)s].%(ext)s",
        "playlist": "%(playlist_title,playlist)s/%(playlist_index)05d - %(title).150B [%(id)s].%(ext)s",
        "channel": "%(channel,uploader)s/%(upload_date)s - %(title).150B [%(id)s].%(ext)s",
    }
    args = list(engine) + [
        "--ignore-config", "--no-color", "--newline", "--progress",
        "--continue", "--no-overwrites",
        "--retries", "10", "--fragment-retries", "10",
        "--socket-timeout", "30",
        "--download-archive", str(archive),
        "-P", str(folder), "-o", patterns[mode],
        "--progress-template",
        "download:__YTDLP_PROGRESS__%(progress._percent_str)s|%(progress._speed_str)s|%(progress._eta_str)s",
        "--print", "after_move:__YTDLP_DONE__%(id)s",
    ]
    if mode == "single":
        args.append("--no-playlist")
    else:
        args.extend(["--yes-playlist", "--ignore-errors"])
    if quality == "1080":
        args.extend(["-f", "bv*[height<=1080]+ba/b[height<=1080]"])
    elif quality == "720":
        args.extend(["-f", "bv*[height<=720]+ba/b[height<=720]"])
    elif quality == "mp3":
        args.extend(["-f", "ba/b", "-x", "--audio-format", "mp3", "--audio-quality", "0"])
    else:
        args.extend(["-f", "bv*+ba/b"])
    if quality != "mp3":
        args.extend(["--merge-output-format", "mp4/mkv"])
    if subtitles:
        args.extend(["--write-subs", "--write-auto-subs", "--sub-langs", "zh.*,en.*"])
    if browser != "不使用":
        args.extend(["--cookies-from-browser", browser.lower()])
    if proxy:
        args.extend(["--proxy", proxy])
    args.append(url)
    return args


def parse_output(line: str) -> tuple:
    match = _PROGRESS.search(line)
    if match:
        return ("progress", min(100.0, float(match.group(1))), match.group(2).strip(), match.group(3).strip())
    match = _DONE.search(line)
    if match:
        return ("done", match.group(1))
    return ("log", line.rstrip("\r\n"))
