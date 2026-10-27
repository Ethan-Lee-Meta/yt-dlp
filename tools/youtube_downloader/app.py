"""Chinese Tkinter desktop UI for downloading YouTube with yt-dlp.

Start from the project root:
    python tools/youtube_downloader/app.py
"""
from __future__ import annotations

import json
import os
import queue
import subprocess
import threading
import tkinter as tk
import uuid
from dataclasses import dataclass
from pathlib import Path
from tkinter import filedialog, messagebox, scrolledtext, ttk

from backend import BROWSERS, MODES, QUALITIES, build_command, check_url, engine_command, parse_output


@dataclass
class Job:
    id: str
    url: str
    mode: str
    status: str = "等待"
    downloaded: int = 0


class DownloaderApp:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title("YouTube 批量下载器 · yt-dlp")
        self.root.geometry("1040x770")
        self.root.minsize(800, 650)

        base = Path(os.getenv("LOCALAPPDATA") or (Path.home() / ".config")) / "yt-dlp-desktop"
        self.config_file = base / "settings.json"
        self.settings = self._load_settings()

        self.jobs: dict[str, Job] = {}
        self.pending: queue.Queue[Job] = queue.Queue()
        self.events: queue.Queue[tuple] = queue.Queue()
        self.worker: threading.Thread | None = None
        self.process: subprocess.Popen | None = None
        self.process_lock = threading.Lock()
        self.cancel_requested = threading.Event()
        self.stop_requested = threading.Event()
        self.closing = False
        self._construct()
        self.root.protocol("WM_DELETE_WINDOW", self._close)
        self.root.after(100, self._poll)

    def _load_settings(self) -> dict:
        try:
            data = json.loads(self.config_file.read_text(encoding="utf-8"))
            return data if isinstance(data, dict) else {}
        except (OSError, ValueError):
            return {}

    def _get(self, key: str, default: str) -> str:
        value = self.settings.get(key, default)
        return value if isinstance(value, str) else default

    def _construct(self):
        s = ttk.Style()
        if "clam" in s.theme_names():
            s.theme_use("clam")
        s.configure("TButton", padding=(10, 6))
        s.configure("Header.TLabel", font=("Microsoft YaHei UI", 15, "bold"))
        s.configure("Treeview", rowheight=26)

        panel = ttk.Frame(self.root, padding=16)
        panel.pack(fill="both", expand=True)
        ttk.Label(panel, text="YouTube 视频 · 播放列表 · 频道下载", style="Header.TLabel").pack(anchor="w")
        ttk.Label(panel, text="每行粘贴一个 YouTube 链接。频道主页将按 yt-dlp 的频道提取规则下载可访问的视频。").pack(
            anchor="w", pady=(4, 12)
        )

        source = ttk.LabelFrame(panel, text="① 视频来源", padding=10)
        source.pack(fill="x")
        self.url_box = tk.Text(source, height=3, font=("Consolas", 10), wrap="none")
        self.url_box.pack(fill="x")
        source_actions = ttk.Frame(source)
        source_actions.pack(fill="x", pady=(8, 0))
        ttk.Label(source_actions, text="下载模式").pack(side="left")
        self.mode_var = tk.StringVar(value=MODES["single"])
        ttk.Combobox(
            source_actions, textvariable=self.mode_var, values=list(MODES.values()),
            width=20, state="readonly",
        ).pack(side="left", padx=(8, 14))
        ttk.Button(source_actions, text="添加到队列", command=self._add_jobs).pack(side="left")
        ttk.Label(source_actions, text="频道全部：粘贴 https://www.youtube.com/@作者").pack(
            side="right"
        )

        settings = ttk.LabelFrame(panel, text="② 下载设置", padding=10)
        settings.pack(fill="x", pady=(12, 0))
        self.folder_var = tk.StringVar(value=self._get("folder", str(Path.home() / "Videos" / "YouTube")))
        ttk.Label(settings, text="保存目录").grid(row=0, column=0, sticky="w")
        ttk.Entry(settings, textvariable=self.folder_var).grid(row=0, column=1, columnspan=5, sticky="ew", padx=8)
        ttk.Button(settings, text="浏览…", command=self._select_folder).grid(row=0, column=6)

        self.quality_var = tk.StringVar(value=self._get("quality", QUALITIES["best"]))
        self.browser_var = tk.StringVar(value=self._get("browser", "不使用"))
        self.subtitle_var = tk.BooleanVar(value=bool(self.settings.get("subtitles", False)))
        self.proxy_var = tk.StringVar(value=self._get("proxy", ""))
        self.engine_var = tk.StringVar(value=self._get("engine", ""))

        ttk.Label(settings, text="画质").grid(row=1, column=0, pady=(10, 0), sticky="w")
        ttk.Combobox(
            settings, textvariable=self.quality_var,
            values=list(QUALITIES.values()), width=17, state="readonly",
        ).grid(row=1, column=1, pady=(10, 0), sticky="w", padx=8)
        ttk.Label(settings, text="浏览器 Cookies").grid(row=1, column=2, pady=(10, 0), sticky="e")
        ttk.Combobox(
            settings, textvariable=self.browser_var, values=BROWSERS, width=11, state="readonly",
        ).grid(row=1, column=3, pady=(10, 0), padx=8)
        ttk.Checkbutton(settings, text="保存中英字幕", variable=self.subtitle_var).grid(
            row=1, column=4, columnspan=3, pady=(10, 0), sticky="w"
        )

        ttk.Label(settings, text="网络代理").grid(row=2, column=0, pady=(10, 0), sticky="w")
        ttk.Entry(settings, textvariable=self.proxy_var).grid(
            row=2, column=1, columnspan=5, pady=(10, 0), sticky="ew", padx=8
        )
        ttk.Label(settings, text="如 http://127.0.0.1:7890").grid(row=2, column=6, pady=(10, 0), sticky="w")
        ttk.Label(settings, text="yt-dlp 程序").grid(row=3, column=0, pady=(10, 0), sticky="w")
        ttk.Entry(settings, textvariable=self.engine_var).grid(
            row=3, column=1, columnspan=5, pady=(10, 0), sticky="ew", padx=8
        )
        ttk.Button(settings, text="选择…", command=self._select_engine).grid(row=3, column=6, pady=(10, 0))
        ttk.Label(settings, text="留空时自动寻找已安装的 yt-dlp（优先使用最新版独立程序）").grid(
            row=4, column=1, columnspan=6, sticky="w", padx=8, pady=(5, 0)
        )
        for col in range(1, 6):
            settings.columnconfigure(col, weight=1)

        tasks = ttk.LabelFrame(panel, text="③ 下载任务队列", padding=10)
        tasks.pack(fill="both", expand=True, pady=(12, 0))
        cols = ("mode", "url", "state", "count")
        self.table = ttk.Treeview(tasks, columns=cols, show="headings", height=8)
        for name, title, width, stretch in (
            ("mode", "模式", 125, False),
            ("url", "YouTube 链接", 525, True),
            ("state", "状态", 155, False),
            ("count", "本次完成", 90, False),
        ):
            self.table.heading(name, text=title)
            self.table.column(name, width=width, stretch=stretch, anchor="w")
        bar = ttk.Scrollbar(tasks, orient="vertical", command=self.table.yview)
        self.table.configure(yscrollcommand=bar.set)
        self.table.pack(side="left", fill="both", expand=True)
        bar.pack(side="right", fill="y")

        actions = ttk.Frame(panel)
        actions.pack(fill="x", pady=(12, 8))
        self.start_button = ttk.Button(actions, text="▶ 开始下载队列", command=self._start)
        self.start_button.pack(side="left")
        ttk.Button(actions, text="■ 停止当前任务", command=self._stop_current).pack(side="left", padx=8)
        ttk.Button(actions, text="停止整个队列", command=self._stop_queue).pack(side="left")
        ttk.Button(actions, text="移除选中的等待任务", command=self._remove_selected).pack(side="right")

        self.progress = ttk.Progressbar(panel, orient="horizontal", mode="determinate", maximum=100)
        self.progress.pack(fill="x")
        self.progress_label = ttk.Label(panel, text="当前视频进度：未开始")
        self.progress_label.pack(anchor="w", pady=(4, 6))
        logs = ttk.LabelFrame(panel, text="实时日志", padding=8)
        logs.pack(fill="both", expand=True)
        self.log_box = scrolledtext.ScrolledText(logs, height=8, wrap="word", state="disabled", font=("Consolas", 9))
        self.log_box.pack(fill="both", expand=True)
        self._log("提示：批量频道下载可能耗时较长；停止后重新添加同一链接可跳过已成功下载的视频。")

    def _select_folder(self):
        selected = filedialog.askdirectory(initialdir=self.folder_var.get())
        if selected:
            self.folder_var.set(selected)

    def _select_engine(self):
        selected = filedialog.askopenfilename(
            title="选择 yt-dlp.exe 或 yt-dlp",
            filetypes=[("Executable", "*.exe"), ("所有文件", "*.*")],
        )
        if selected:
            self.engine_var.set(selected)

    def _add_jobs(self):
        urls = [x.strip() for x in self.url_box.get("1.0", "end").splitlines() if x.strip()]
        if not urls:
            messagebox.showinfo("缺少链接", "每行粘贴一个 YouTube 链接。")
            return
        mode = next((key for key, label in MODES.items() if label == self.mode_var.get()), "single")
        rejected = []
        count = 0
        for original in urls:
            try:
                url = check_url(original, mode)
            except ValueError as exc:
                rejected.append(f"{original[:100]}\n{exc}")
                continue
            if any(job.url == url and job.mode == mode and job.status in ("等待", "下载中") for job in self.jobs.values()):
                rejected.append(f"{url[:100]}\n已在队列中")
                continue
            job = Job(uuid.uuid4().hex, url, mode)
            self.jobs[job.id] = job
            self.pending.put(job)
            self.table.insert("", "end", iid=job.id, values=(MODES[mode], url, job.status, "0"))
            count += 1
        if count:
            self.url_box.delete("1.0", "end")
            self._log(f"已加入 {count} 个任务")
        if rejected:
            messagebox.showwarning("部分链接未加入", "\n\n".join(rejected[:6]))

    def _remove_selected(self):
        # The Queue cannot remove arbitrary items safely; mark and skip them in the worker.
        for iid in self.table.selection():
            job = self.jobs[iid]
            if job.status == "等待":
                job.status = "已移除"
                self.table.set(iid, "state", job.status)

    def _snapshot(self) -> dict:
        quality = next((key for key, text in QUALITIES.items() if text == self.quality_var.get()), "best")
        return {
            "folder": self.folder_var.get().strip(),
            "quality": quality,
            "subtitles": self.subtitle_var.get(),
            "browser": self.browser_var.get(),
            "proxy": self.proxy_var.get().strip(),
            "engine": self.engine_var.get().strip(),
        }

    def _save_settings(self):
        data = {
            "folder": self.folder_var.get(),
            "quality": self.quality_var.get(),
            "subtitles": self.subtitle_var.get(),
            "browser": self.browser_var.get(),
            "proxy": self.proxy_var.get(),
            "engine": self.engine_var.get(),
        }
        try:
            self.config_file.parent.mkdir(parents=True, exist_ok=True)
            self.config_file.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        except OSError as exc:
            self._log(f"无法保存设置：{exc}")

    def _start(self):
        if self.worker and self.worker.is_alive():
            return
        if self.pending.empty():
            messagebox.showinfo("队列为空", "请先添加视频链接。")
            return
        settings = self._snapshot()
        if not settings["folder"]:
            messagebox.showerror("保存目录", "请选择下载保存目录")
            return
        try:
            from backend import check_proxy
            check_proxy(settings["proxy"])
            engine_command(settings["engine"])
        except ValueError as exc:
            messagebox.showerror("设置错误", str(exc))
            return
        self._save_settings()
        self.stop_requested.clear()
        self.cancel_requested.clear()
        self.start_button.configure(state="disabled")
        self.worker = threading.Thread(target=self._run_queue, args=(settings,), daemon=True)
        self.worker.start()

    def _run_queue(self, settings: dict):
        try:
            engine = engine_command(settings["engine"])
            while not self.stop_requested.is_set():
                try:
                    job = self.pending.get_nowait()
                except queue.Empty:
                    break
                if job.status != "等待":
                    continue
                self.cancel_requested.clear()
                self.events.put(("started", job.id))
                try:
                    args = build_command(
                        engine, job.url, job.mode, Path(settings["folder"]),
                        settings["quality"], settings["subtitles"],
                        settings["browser"], settings["proxy"],
                    )
                    self.events.put(("log", f"\n开始：{MODES[job.mode]} | {job.url}"))
                    flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
                    proc = subprocess.Popen(
                        args, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                        text=True, encoding="utf-8", errors="replace",
                        bufsize=1, creationflags=flags,
                        env={**os.environ, "PYTHONIOENCODING": "utf-8"},
                    )
                    with self.process_lock:
                        self.process = proc
                        if self.cancel_requested.is_set() or self.stop_requested.is_set():
                            proc.terminate()
                    assert proc.stdout is not None
                    with proc.stdout:
                        for line in proc.stdout:
                            info = parse_output(line)
                            self.events.put((info[0], job.id, *info[1:]))
                    code = proc.wait()
                    if self.cancel_requested.is_set() or self.stop_requested.is_set():
                        state = "已停止（可重新下载）"
                    elif code != 0:
                        state = f"失败（退出码 {code}）"
                    else:
                        state = "已完成" if job.mode == "single" else "已完成（检查跳过项）"
                    self.events.put(("finished", job.id, state))
                except (OSError, ValueError) as exc:
                    self.events.put(("log", f"错误：{exc}"))
                    self.events.put(("finished", job.id, "失败"))
                finally:
                    with self.process_lock:
                        self.process = None
            self.events.put(("log", "队列处理结束；可重新添加同一频道链接下载新视频。"))
        finally:
            self.events.put(("idle",))

    def _stop_current(self):
        with self.process_lock:
            proc = self.process
            if proc is None or proc.poll() is not None:
                return
            self.cancel_requested.set()
            try:
                proc.terminate()
            except OSError:
                pass
        self._log("已请求停止当前任务；已经完整下载的视频会保留。")

    def _stop_queue(self):
        self.stop_requested.set()
        self._stop_current()
        self._log("已请求停止队列；未开始的任务可重新点击开始。")

    def _log(self, line: str):
        self.log_box.configure(state="normal")
        self.log_box.insert("end", line + "\n")
        # Retain the latest ~800 lines to avoid unbounded RAM use on huge channels.
        lines = int(self.log_box.index("end-1c").split(".")[0])
        if lines > 800:
            self.log_box.delete("1.0", f"{lines - 700}.0")
        self.log_box.see("end")
        self.log_box.configure(state="disabled")

    def _poll(self):
        if self.closing:
            return
        for _ in range(150):
            try:
                event = self.events.get_nowait()
            except queue.Empty:
                break
            kind = event[0]
            if kind == "log":
                # Generic worker logs are ("log", task_id, line); local logs ("log", line).
                self._log(event[-1])
                continue
            if kind == "idle":
                self.start_button.configure(state="normal")
                continue
            _, task_id, *data = event
            if task_id not in self.jobs:
                continue
            job = self.jobs[task_id]
            if kind == "started":
                job.status = "下载中"
                self.progress["value"] = 0
                self.progress_label.configure(text=f"当前视频进度：正在获取 {job.url[:85]}")
            elif kind == "progress":
                percent, speed, eta = data
                self.progress["value"] = percent
                self.progress_label.configure(
                    text=f"当前视频进度：{percent:.1f}%    速度：{speed or '未知'}    ETA：{eta or '未知'}"
                )
            elif kind == "done":
                job.downloaded += 1
                self._log(f"下载完成视频 ID：{data[0]}")
            elif kind == "finished":
                job.status = data[0]
                self._log(f"任务 {MODES[job.mode]}：{job.status}")
            self.table.set(task_id, "state", job.status)
            self.table.set(task_id, "count", str(job.downloaded))
        self.root.after(100, self._poll)

    def _close(self):
        if self.worker and self.worker.is_alive():
            if not messagebox.askyesno("退出", "下载仍在进行。退出会停止当前任务，继续吗？"):
                return
        self.closing = True
        self.stop_requested.set()
        with self.process_lock:
            if self.process and self.process.poll() is None:
                try:
                    self.process.terminate()
                except OSError:
                    pass
        self._save_settings()
        self.root.destroy()


def main():
    root = tk.Tk()
    DownloaderApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
