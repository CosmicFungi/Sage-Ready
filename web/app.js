(() => {
  const $ = (id) => document.getElementById(id);

  const pathInput = $("comfy-path");
  const pathError = $("path-error");
  const btnScan = $("btn-scan");
  const btnFix = $("btn-fix");
  const btnRepair = $("btn-repair");
  const btnVerify = $("btn-verify");
  const btnCopy = $("btn-copy");
  const btnHelper = $("btn-helper");
  const btnRescan = $("btn-rescan");
  const stepReport = $("step-report");
  const stepReady = $("step-ready");
  const checklist = $("checklist");
  const summary = $("summary");
  const envLine = $("env-line");
  const logPanel = $("log-panel");
  const logOutput = $("log-output");
  const launchCmd = $("launch-cmd");
  const readyCopy = $("ready-copy");
  const helperHint = $("helper-hint");
  const shell = document.querySelector(".shell");

  const STATUS_GLYPH = { ok: "✓", warn: "!", fail: "✕", skip: "–" };
  const DEFAULT_BUTTONS = {
    scan: "Scan",
    fix: "Install & Fix",
    repair: "Repair",
    verify: "Test GPU",
  };
  const PATH_KEY = "sageReady.comfyPath";
  const PATH_KEY_VER = "sageReady.comfyPath.v";
  const PATH_SCHEMA = "2"; // bump to ignore old machine-specific saved paths

  let lastPath = "";
  let lastScan = null;
  let busyDepth = 0;
  let activeBusyBtn = null;

  function isExampleOrStalePath(path) {
    const t = (path || "").trim().toLowerCase();
    if (!t) return true;
    // Never restore one-off install layouts or example text
    if (t.includes("comfyui-easy-install")) return true;
    if (t.includes("example:")) return true;
    return false;
  }

  function setPathError(msg) {
    if (!msg) {
      pathError.textContent = "";
      pathError.classList.add("hidden");
      return;
    }
    pathError.textContent = msg;
    pathError.classList.remove("hidden");
  }

  function setBusy(state, btn, label) {
    if (state) {
      busyDepth += 1;
      activeBusyBtn = btn || null;
      [btnScan, btnFix, btnRepair, btnVerify, btnHelper].forEach((b) => {
        b.disabled = true;
      });
      if (btn && label) btn.textContent = label;
    } else {
      busyDepth = Math.max(0, busyDepth - 1);
      if (busyDepth === 0) {
        [btnScan, btnFix, btnRepair, btnVerify, btnHelper].forEach((b) => {
          b.disabled = false;
        });
        btnScan.textContent = DEFAULT_BUTTONS.scan;
        btnFix.textContent = DEFAULT_BUTTONS.fix;
        btnRepair.textContent = DEFAULT_BUTTONS.repair;
        btnVerify.textContent = DEFAULT_BUTTONS.verify;
        activeBusyBtn = null;
      }
    }
  }

  function show(el) {
    el.classList.remove("hidden");
  }

  function hide(el) {
    el.classList.add("hidden");
  }

  function friendlyError(err) {
    const text = String(err || "Something went wrong");
    if (text.includes("Failed to fetch") || text.includes("NetworkError")) {
      return "Can't reach Sage Ready. Is the app still running?";
    }
    return text;
  }

  function renderChecks(checks) {
    checklist.innerHTML = "";
    checks.forEach((item) => {
      const li = document.createElement("li");
      const mark = document.createElement("div");
      mark.className = `check-mark ${item.status}`;
      mark.textContent = STATUS_GLYPH[item.status] || "·";

      const body = document.createElement("div");
      const title = document.createElement("p");
      title.className = "check-title";
      title.textContent = item.title;
      body.appendChild(title);

      if (item.detail) {
        const detail = document.createElement("p");
        detail.className = "check-detail";
        detail.textContent = item.detail;
        body.appendChild(detail);
      }
      if (item.fix_hint && item.status !== "ok") {
        const fix = document.createElement("p");
        fix.className = "check-fix";
        fix.textContent = item.fix_hint;
        body.appendChild(fix);
      }

      li.appendChild(mark);
      li.appendChild(body);
      checklist.appendChild(li);
    });
  }

  function formatEnv(env) {
    if (!env) return "";
    const labels = {
      portable: "Portable",
      venv: "Virtual env",
      active_venv: "Active virtual env",
      conda: "Conda",
      system: "System",
      unknown: "Unknown",
    };
    const raw = env.environment_type || "unknown";
    const fallback = raw.includes("(fallback)");
    const key = raw.replace(/\s*\(fallback\)\s*/g, "").trim();
    const type = (labels[key] || key) + (fallback ? " (fallback)" : "");
    return [
      `Environment: ${type}`,
      env.python_version && `Python ${env.python_version}`,
      env.torch_version && `PyTorch ${env.torch_version}`,
      env.gpu_name,
    ]
      .filter(Boolean)
      .join(" · ");
  }

  async function performScan() {
    const comfy_path = pathInput.value.trim();
    if (!comfy_path) {
      setPathError("Enter the path to your ComfyUI folder (the one with main.py).");
      pathInput.focus();
      return null;
    }
    setPathError("");
    lastPath = comfy_path;
    localStorage.setItem(PATH_KEY, comfy_path);
    localStorage.setItem(PATH_KEY_VER, PATH_SCHEMA);
    hide(stepReady);
    shell.classList.remove("ready-mode");

    const res = await fetch("/api/scan", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ comfy_path }),
    });
    let data;
    try {
      data = await res.json();
    } catch {
      throw new Error(`Scan failed (HTTP ${res.status})`);
    }
    // 403 cloud block, or FastAPI 422 validation errors
    if (!res.ok) {
      let msg = `Scan failed (HTTP ${res.status})`;
      if (data && (data.error || data.detail) && res.status === 403) {
        msg = [data.error, data.detail].filter(Boolean).join("\n\n");
      } else {
        const detail = data && data.detail;
        if (typeof detail === "string") {
          msg = detail;
        } else if (Array.isArray(detail) && detail.length) {
          msg = detail
            .map((d) => (typeof d === "string" ? d : d.msg || JSON.stringify(d)))
            .join("\n")
            .replace(/^Value error,\s*/i, "");
        }
      }
      show(stepReport);
      summary.textContent = msg.split("\n")[0];
      envLine.textContent = "";
      renderChecks([
        {
          id: "error",
          title: "Could not scan",
          status: "fail",
          detail: msg,
          fix_hint:
            "Run Sage Ready on the same computer as ComfyUI, then paste a local folder path.",
        },
      ]);
      lastScan = { ok: false, error: msg };
      return lastScan;
    }
    lastScan = data;
    if (!data.ok) {
      show(stepReport);
      summary.textContent = data.error || "Scan failed";
      envLine.textContent = "";
      renderChecks([
        {
          id: "error",
          title: "Could not scan",
          status: "fail",
          detail: data.error || "Unknown error",
          fix_hint:
            "Check that the path points at a ComfyUI folder with main.py. " +
            "Sage Ready must run on the same PC as ComfyUI.",
        },
      ]);
      return data;
    }

    show(stepReport);
    summary.textContent = data.summary;
    envLine.textContent = formatEnv(data.env);
    renderChecks(data.checks || []);
    btnFix.textContent = DEFAULT_BUTTONS.fix;

    if (data.ready) {
      await showReady(comfy_path, data.summary);
    }
    return data;
  }

  async function scan() {
    setBusy(true, btnScan, "Scanning…");
    try {
      await performScan();
    } catch (err) {
      show(stepReport);
      summary.textContent = friendlyError(err);
      envLine.textContent = "";
      renderChecks([
        {
          id: "error",
          title: "Scan interrupted",
          status: "fail",
          detail: friendlyError(err),
          fix_hint: "Confirm Sage Ready is running, then try Scan again.",
        },
      ]);
    } finally {
      setBusy(false);
    }
  }

  async function runInstall(mode) {
    if (!lastPath) {
      await scan();
      if (!lastPath) return;
    }
    const btn = mode === "repair" ? btnRepair : btnFix;
    const label = mode === "repair" ? "Repairing…" : "Installing…";
    setBusy(true, btn, label);
    logOutput.textContent = "";
    logPanel.open = true;
    hide(stepReady);
    shell.classList.remove("ready-mode");

    try {
      const res = await fetch("/api/install", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ comfy_path: lastPath, mode }),
      });
      if (!res.ok) {
        throw new Error(`Install failed (HTTP ${res.status})`);
      }

      const reader = res.body.getReader();
      const decoder = new TextDecoder();
      let buffer = "";
      let installOk = false;
      let installError = "";

      while (true) {
        const { value, done } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });
        const chunks = buffer.split("\n\n");
        buffer = chunks.pop() || "";
        for (const chunk of chunks) {
          const line = chunk
            .split("\n")
            .filter((l) => l.startsWith("data: "))
            .map((l) => l.slice(6))
            .join("");
          if (!line) continue;
          let evt;
          try {
            evt = JSON.parse(line);
          } catch {
            continue;
          }
          if (evt.type === "log") {
            logOutput.textContent += `${evt.line}\n`;
            logOutput.scrollTop = logOutput.scrollHeight;
          } else if (evt.type === "result") {
            installOk = !!evt.ok;
            if (!evt.ok) installError = evt.error || "Install failed";
          }
        }
      }

      if (!installOk && installError) {
        summary.textContent = installError;
      }

      if (activeBusyBtn) activeBusyBtn.textContent = "Re-scanning…";
      const data = await performScan();
      if (data && data.ok) {
        if (!data.ready && !installOk) {
          summary.textContent =
            installError ||
            data.summary ||
            "Install finished with issues — see the checklist.";
        }
      } else if (!data) {
        summary.textContent = installError || "Re-scan failed";
      } else if (!data.ok) {
        summary.textContent = data.error || installError || "Re-scan failed";
      }
    } catch (err) {
      summary.textContent = friendlyError(err);
      logOutput.textContent += `\n${friendlyError(err)}\n`;
    } finally {
      setBusy(false);
    }
  }

  async function verifyOnly() {
    if (!lastPath) {
      setPathError("Scan a ComfyUI folder first.");
      return;
    }
    setBusy(true, btnVerify, "Testing…");
    try {
      const res = await fetch("/api/verify", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ comfy_path: lastPath }),
      });
      const data = await res.json();
      // Re-scan so Ready is only from the full checklist — never from verify alone
      if (activeBusyBtn) activeBusyBtn.textContent = "Re-scanning…";
      await performScan();
      if (!data.ok && !data.skipped) {
        summary.textContent =
          data.detail || data.error || "GPU attention test did not pass.";
      } else if (data.skipped) {
        summary.textContent =
          data.detail ||
          "GPU test skipped — Ready cannot complete without an NVIDIA GPU.";
      }
    } catch (err) {
      summary.textContent = friendlyError(err);
    } finally {
      setBusy(false);
    }
  }

  async function showReady(comfy_path, summaryText) {
    show(stepReady);
    shell.classList.add("ready-mode");
    readyCopy.textContent =
      summaryText ||
      "SageAttention imports cleanly, and a live GPU test matched PyTorch’s built-in attention. Restart ComfyUI with the command below.";
    try {
      const res = await fetch("/api/launch-command", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ comfy_path }),
      });
      const data = await res.json();
      if (data.ok) {
        launchCmd.textContent = data.command;
      }
    } catch {
      launchCmd.textContent = "python main.py --use-sage-attention";
    }
    helperHint.textContent =
      "ComfyUI must be started with --use-sage-attention or SageAttention will not be used. Fully restart ComfyUI if it was already open. Optional: save a helper script next to main.py.";
  }

  async function saveHelper() {
    if (!lastPath) return;
    setBusy(true, btnHelper, "Saving…");
    try {
      const res = await fetch("/api/write-helper", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ comfy_path: lastPath }),
      });
      const data = await res.json();
      if (data.ok && data.helper_script) {
        helperHint.textContent = `Shortcut saved: ${data.helper_script} — run it so ComfyUI starts with SageAttention enabled. Restart ComfyUI if it was already open.`;
      } else {
        helperHint.textContent = data.detail || "Could not write helper script.";
      }
    } catch (err) {
      helperHint.textContent = friendlyError(err);
    } finally {
      setBusy(false);
    }
  }

  btnScan.addEventListener("click", scan);
  pathInput.addEventListener("keydown", (e) => {
    if (e.key === "Enter") scan();
  });
  pathInput.addEventListener("input", () => setPathError(""));
  btnFix.addEventListener("click", () => runInstall("install"));
  btnRepair.addEventListener("click", () => runInstall("repair"));
  btnVerify.addEventListener("click", verifyOnly);
  btnHelper.addEventListener("click", saveHelper);
  btnRescan.addEventListener("click", () => {
    hide(stepReady);
    shell.classList.remove("ready-mode");
    scan();
  });
  btnCopy.addEventListener("click", async () => {
    const text = launchCmd.textContent || "";
    try {
      await navigator.clipboard.writeText(text);
      btnCopy.textContent = "Copied";
      setTimeout(() => {
        btnCopy.textContent = "Copy";
      }, 1200);
    } catch {
      const range = document.createRange();
      range.selectNodeContents(launchCmd);
      const sel = window.getSelection();
      sel.removeAllRanges();
      sel.addRange(range);
      btnCopy.textContent = "Selected";
      setTimeout(() => {
        btnCopy.textContent = "Copy";
      }, 1500);
    }
  });

  const savedVer = localStorage.getItem(PATH_KEY_VER);
  const saved = localStorage.getItem(PATH_KEY);
  if (savedVer === PATH_SCHEMA && saved && !isExampleOrStalePath(saved)) {
    pathInput.value = saved;
  } else {
    localStorage.removeItem(PATH_KEY);
    localStorage.setItem(PATH_KEY_VER, PATH_SCHEMA);
    pathInput.value = "";
  }

  // Show which machine this UI is talking to (blocks cloud confusion)
  (async function showHost() {
    const badge = $("host-badge");
    const warn = $("host-warn");
    if (!badge) return;
    try {
      const res = await fetch("/api/health");
      const data = await res.json();
      const localPage =
        location.hostname === "127.0.0.1" ||
        location.hostname === "localhost";

      if (data.cloud_blocked || data.status === "cloud_blocked") {
        badge.textContent = `BLOCKED · cloud/agent host · v${data.version || "?"}`;
        badge.classList.add("is-remote");
        warn.classList.remove("hidden");
        warn.textContent =
          (data.detail || data.cloud_block_reason || "Cloud host detected") +
          "\n\nDownload the app onto your Windows PC and run:  py app.py\n" +
          "Then open ONLY http://127.0.0.1:8765";
        pathInput.disabled = true;
        btnScan.disabled = true;
        return;
      }

      const label = data.is_windows
        ? `Local Windows · v${data.version}`
        : `Local ${data.platform || "PC"} · v${data.version}`;
      badge.textContent = label;

      if (!localPage) {
        badge.classList.add("is-remote");
        warn.classList.remove("hidden");
        warn.textContent =
          "Wrong URL. Sage Ready is local-only — open http://127.0.0.1:8765 after running py app.py on your PC.";
        pathInput.disabled = true;
        btnScan.disabled = true;
      } else if (!data.is_windows) {
        badge.classList.add("is-remote");
        warn.classList.remove("hidden");
        warn.textContent =
          "This PC is not Windows. For a Windows ComfyUI portable install (example: B:\\ComfyUI_windows_portable\\ComfyUI), run Sage Ready on that Windows machine.";
      } else {
        badge.classList.remove("is-remote");
        warn.classList.add("hidden");
        warn.textContent = "";
      }
    } catch {
      badge.textContent = "Can't reach Sage Ready server";
      badge.classList.add("is-remote");
    }
  })();
})();
