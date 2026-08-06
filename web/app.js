(() => {
  const $ = (id) => document.getElementById(id);

  const pathInput = $("comfy-path");
  const btnScan = $("btn-scan");
  const btnFix = $("btn-fix");
  const btnRepair = $("btn-repair");
  const btnVerify = $("btn-verify");
  const btnCopy = $("btn-copy");
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

  const STATUS_GLYPH = {
    ok: "✓",
    warn: "!",
    fail: "✕",
    skip: "–",
  };

  let lastPath = "";
  let busy = false;

  function setBusy(state, label) {
    busy = state;
    [btnScan, btnFix, btnRepair, btnVerify].forEach((btn) => {
      btn.disabled = state;
    });
    if (state && label) {
      btnScan.textContent = label;
    } else {
      btnScan.textContent = "Scan";
    }
  }

  function show(el) {
    el.classList.remove("hidden");
  }

  function hide(el) {
    el.classList.add("hidden");
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

  async function scan() {
    const comfy_path = pathInput.value.trim();
    if (!comfy_path) {
      pathInput.focus();
      return;
    }
    lastPath = comfy_path;
    setBusy(true, "Scanning…");
    hide(stepReady);
    try {
      const res = await fetch("/api/scan", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ comfy_path }),
      });
      const data = await res.json();
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
            fix_hint: "Check that the path points at a ComfyUI folder with main.py.",
          },
        ]);
        return;
      }

      show(stepReport);
      summary.textContent = data.summary;
      const env = data.env || {};
      envLine.textContent = [
        env.environment_type && `Env: ${env.environment_type}`,
        env.python_version && `Python ${env.python_version}`,
        env.torch_version && `Torch ${env.torch_version}`,
        env.gpu_name,
      ]
        .filter(Boolean)
        .join(" · ");

      renderChecks(data.checks || []);

      const needsFix = (data.checks || []).some(
        (c) => c.status === "fail" || (c.id === "sageattention" && c.status === "warn")
      );
      btnFix.textContent = needsFix ? "Install & Fix" : "Reinstall";
      btnFix.style.display = "";

      if (data.ready) {
        await showReady(comfy_path, data);
      }
    } catch (err) {
      show(stepReport);
      summary.textContent = String(err);
      renderChecks([]);
    } finally {
      setBusy(false);
    }
  }

  async function runInstall(mode) {
    if (!lastPath) {
      await scan();
      if (!lastPath) return;
    }
    setBusy(true, mode === "repair" ? "Repairing…" : "Installing…");
    logOutput.textContent = "";
    logPanel.open = true;

    try {
      const res = await fetch("/api/install", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ comfy_path: lastPath, mode }),
      });

      const reader = res.body.getReader();
      const decoder = new TextDecoder();
      let buffer = "";

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
            if (!evt.ok) {
              summary.textContent = evt.error || "Install failed";
            }
          }
        }
      }

      await scan();
      const verifyRes = await fetch("/api/verify", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ comfy_path: lastPath }),
      });
      const verifyData = await verifyRes.json();
      if (verifyData.ok) {
        await showReady(lastPath, { summary: verifyData.detail });
      } else if (!verifyData.skipped) {
        summary.textContent =
          verifyData.detail ||
          verifyData.error ||
          "Install finished, but kernel verification did not pass.";
      }
    } catch (err) {
      summary.textContent = String(err);
      logOutput.textContent += `\n${err}\n`;
    } finally {
      setBusy(false);
    }
  }

  async function verifyOnly() {
    if (!lastPath) return;
    setBusy(true, "Verifying…");
    try {
      const res = await fetch("/api/verify", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ comfy_path: lastPath }),
      });
      const data = await res.json();
      if (data.ok) {
        await showReady(lastPath, { summary: data.detail });
      } else {
        summary.textContent = data.detail || data.error || "Verification failed";
        await scan();
      }
    } catch (err) {
      summary.textContent = String(err);
    } finally {
      setBusy(false);
    }
  }

  async function showReady(comfy_path, scanData) {
    show(stepReady);
    if (scanData && scanData.summary) {
      readyCopy.textContent = scanData.summary;
    }
    try {
      const res = await fetch("/api/launch-command", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ comfy_path }),
      });
      const data = await res.json();
      if (data.ok) {
        launchCmd.textContent = data.command;
        helperHint.textContent = data.helper_script
          ? `Helper script written: ${data.helper_script}`
          : "";
      }
    } catch {
      launchCmd.textContent = "python main.py --use-sage-attention";
    }
  }

  btnScan.addEventListener("click", scan);
  pathInput.addEventListener("keydown", (e) => {
    if (e.key === "Enter") scan();
  });
  btnFix.addEventListener("click", () => runInstall("install"));
  btnRepair.addEventListener("click", () => runInstall("repair"));
  btnVerify.addEventListener("click", verifyOnly);
  btnRescan.addEventListener("click", () => {
    hide(stepReady);
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
      btnCopy.textContent = "Select & copy";
    }
  });

  // Restore last path
  const saved = localStorage.getItem("sageReady.comfyPath");
  if (saved) pathInput.value = saved;
  pathInput.addEventListener("change", () => {
    localStorage.setItem("sageReady.comfyPath", pathInput.value.trim());
  });
})();
