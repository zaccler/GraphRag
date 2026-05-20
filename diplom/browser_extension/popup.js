const DEFAULT_API = "http://127.0.0.1:8099";

const $ = (id) => document.getElementById(id);

let apiUrl = DEFAULT_API;
let role = "";
let userEmail = "";
let lastOutput = "";
let chatLogsByUser = {};
let authDraft = {};

function outputMode() {
  return document.querySelector('input[name="outputMode"]:checked')?.value || "text";
}

function formatLastResult(data) {
  if (!data || typeof data !== "object") return "last_result: none";

  const result = data.result || {};
  const skipped = Array.isArray(result.skipped) ? result.skipped : [];
  const errors = Array.isArray(result.errors) ? result.errors : [];
  const files = Array.isArray(result.files) ? result.files : [];
  const lines = [
    `task: ${data.kind || "unknown"}`,
    `status: ${data.status || "done"}`,
  ];

  if (data.max_sources !== undefined && data.max_sources !== null) lines.push(`limit: ${data.max_sources}`);
  if (data.force !== undefined) lines.push(`force: ${data.force}`);
  if (data.indexed !== undefined) lines.push(`indexed to Dgraph: ${data.indexed}`);
  if (data.index_reason) lines.push(`index reason: ${data.index_reason}`);
  if (data.target_dir) lines.push(`target: ${data.target_dir}`);
  if (data.saved_path) lines.push(`saved: ${data.saved_path}`);
  if (data.files_found !== undefined) lines.push(`files found: ${data.files_found}`);
  if (data.text_db_mirror) {
    lines.push(`sheet rows: ${data.text_db_mirror.records || 0}`);
    lines.push(`sheet logged: ${data.text_db_mirror.sheet_logged === true}`);
    if (data.text_db_mirror.reason) lines.push(`sheet note: ${data.text_db_mirror.reason}`);
    if (data.text_db_mirror.error) lines.push(`sheet error: ${data.text_db_mirror.error}`);
  }
  if (result.total_sources !== undefined) lines.push(`total sources: ${result.total_sources}`);
  if (result.checked !== undefined) lines.push(`checked: ${result.checked}`);
  if (result.attempted !== undefined) lines.push(`attempted: ${result.attempted}`);
  if (result.count !== undefined) lines.push(`parsed: ${result.count}`);
  if (files.length) lines.push(`files: ${files.length}`);
  if (skipped.length) lines.push(`skipped: ${skipped.length}`);
  if (errors.length) lines.push(`errors: ${errors.length}`);
  if (data.error) lines.push(`error: ${data.error}`);

  const firstSkipped = skipped[0];
  if (firstSkipped) {
    lines.push(`first skipped: ${firstSkipped.code || "source"} (${firstSkipped.reason || "skipped"})`);
  }

  const firstError = errors[0];
  if (firstError) {
    lines.push(`first error: ${firstError.code || "source"} - ${firstError.error || "unknown"}`);
  }

  return lines.join("\n");
}


function formatDebugOutput(data) {
  if (!data || typeof data !== "object") return compactText(data);

  const lines = [
    "ASK DEBUG",
    `response_type: ${data.response_type || "unknown"}`,
    "",
    "answer:",
    data.answer || "none",
  ];

  if (data.retrieved_context) {
    lines.push("", "retrieved_context:", data.retrieved_context);
  }

  if (data.raw_result !== undefined && data.raw_result !== null) {
    lines.push("", "raw_result:", JSON.stringify(data.raw_result, null, 2));
  }

  return lines.join("\n");
}

function compactText(data) {
  if (typeof data === "string") return data;
  if (!data || typeof data !== "object") return String(data);
  if (data.response_type || data.retrieved_context || data.raw_result) return formatDebugOutput(data);
  if (data.answer) return data.answer;
  if (data.preview) {
    const limit = data.request?.max_sources || "all";
    const force = data.request?.force === true;
    return [
      `settings: ${data.path}`,
      `limit: ${limit}`,
      `force: ${force}`,
      "press Parse file or Enter to start.",
    ].join("\n");
  }
  if (data.action && data.response) {
    const limit = data.request?.max_sources || "all";
    const force = data.request?.force === true;
    return [
      `accepted: ${data.action}`,
      `limit: ${limit}`,
      `force: ${force}`,
      data.response?.text_db_mirror
        ? `sheet rows: ${data.response.text_db_mirror.records || 0}, logged: ${data.response.text_db_mirror.sheet_logged === true}`
        : "",
      "status will update automatically; press Status for the latest result.",
    ].filter(Boolean).join("\n");
  }
  if (data.status) return `status: ${data.status}`;
  if (data.detail) return typeof data.detail === "string" ? data.detail : JSON.stringify(data.detail);
  if (data.is_processing !== undefined) {
    const lines = [
      `processing: ${data.is_processing}`,
      `phase: ${data.phase}`,
      `last_error: ${data.last_error || "none"}`,
    ];
    if (data.last_result) {
      lines.push("", formatLastResult(data.last_result));
    }
    return lines.join("\n");
  }
  if (data.last_result) return formatLastResult(data.last_result);
  if (data.count !== undefined) return `count: ${data.count}`;
  return JSON.stringify(data, null, 2);
}

function writeOutput(data) {
  lastOutput = data;
  const text = outputMode() === "json" ? JSON.stringify(data, null, 2) : compactText(data);
  $("log").textContent = text;
}

function currentHistoryKey() {
  if (role === "admin") return "__admin__";
  return userEmail || "__guest__";
}

function appendTextWithLinks(node, text) {
  const urlPattern = /https?:\/\/[^\s<>"'`)\]]+/g;
  let cursor = 0;

  for (const match of text.matchAll(urlPattern)) {
    const rawUrl = match[0];
    const start = match.index || 0;
    const cleanUrl = rawUrl.replace(/[.,;:]+$/g, "");
    const tail = rawUrl.slice(cleanUrl.length);

    if (start > cursor) node.appendChild(document.createTextNode(text.slice(cursor, start)));

    const link = document.createElement("a");
    link.href = cleanUrl;
    link.textContent = cleanUrl.length > 56 ? `${cleanUrl.slice(0, 53)}...` : cleanUrl;
    link.title = cleanUrl;
    link.onclick = (event) => {
      event.preventDefault();
      chrome.tabs.create({ url: cleanUrl });
    };
    node.appendChild(link);

    if (tail) node.appendChild(document.createTextNode(tail));
    cursor = start + rawUrl.length;
  }

  if (cursor < text.length) node.appendChild(document.createTextNode(text.slice(cursor)));
}

function setButtonState(button, state, label = "") {
  if (!button) return;
  if (!button.dataset.defaultText) button.dataset.defaultText = button.textContent;

  button.classList.remove("loading", "busy", "done", "failed");
  button.disabled = state === "busy";

  if (state === "idle") {
    button.textContent = button.dataset.defaultText;
    return;
  }

  button.classList.add(state);
  if (label) button.textContent = label;
}

function finishButton(button, ok, label) {
  setButtonState(button, ok ? "done" : "failed", label);
  setTimeout(() => setButtonState(button, "idle"), 1300);
}

function setLoading(button, value, label = "Wait") {
  if (value) {
    setButtonState(button, "busy", label);
  } else {
    setButtonState(button, "idle");
  }
}

function setApiState(data, failed = false) {
  const node = $("apiStatusText");
  if (failed) {
    node.textContent = "API: offline";
    node.className = "api-state bad";
    return;
  }
  const busy = data?.is_processing ? "busy" : "idle";
  const phase = data?.phase || "unknown";
  node.textContent = `API: ${busy} · ${phase}`;
  node.className = data?.is_processing ? "api-state warn" : "api-state ok";
}

async function loadSettings() {
  const localData = await chrome.storage.local.get(["apiUrl", "role", "chatLogs", "chatLogsByUser"]);
  const sessionData = await chrome.storage.session.get(["role", "userEmail", "authDraft"]);
  apiUrl = localData.apiUrl || DEFAULT_API;
  role = sessionData.role || "";
  userEmail = sessionData.userEmail || "";
  authDraft = sessionData.authDraft && typeof sessionData.authDraft === "object" ? sessionData.authDraft : {};
  chatLogsByUser =
    localData.chatLogsByUser && typeof localData.chatLogsByUser === "object" ? localData.chatLogsByUser : {};
  if (Array.isArray(localData.chatLogs) && !chatLogsByUser.__legacy__) {
    chatLogsByUser.__legacy__ = localData.chatLogs;
    await chrome.storage.local.set({ chatLogsByUser });
  }
  if (localData.role) await chrome.storage.local.remove(["role"]);
  $("apiUrl").value = apiUrl;
  renderRole();
  restoreAuthDraft();
}

async function saveSettings() {
  apiUrl = $("apiUrl").value.trim() || DEFAULT_API;
  await chrome.storage.local.set({ apiUrl });
  writeOutput(`API сохранен: ${apiUrl}`);
}

async function loadCodes() {
  const response = await fetch(chrome.runtime.getURL("access_codes.json"));
  return await response.json();
}

function setAuthMode(mode) {
  const registerMode = mode === "register";
  $("codeLoginForm").classList.toggle("hidden", registerMode);
  $("registerForm").classList.toggle("hidden", !registerMode);
  $("showLoginBtn").classList.toggle("active", !registerMode);
  $("showRegisterBtn").classList.toggle("active", registerMode);
  $("loginError").classList.add("hidden");
  $("registerError").classList.add("hidden");
  if (!registerMode) {
    $("registerSent").classList.add("hidden");
    $("emailCodeBlock").classList.add("hidden");
  }
}

async function saveAuthDraft(changes = {}) {
  authDraft = { ...authDraft, ...changes };
  await chrome.storage.session.set({ authDraft });
}

async function clearAuthDraft() {
  authDraft = {};
  await chrome.storage.session.remove(["authDraft"]);
}

function restoreAuthDraft() {
  if (!authDraft.mode) return;

  setAuthMode(authDraft.mode);
  if (authDraft.email) $("registerEmail").value = authDraft.email;
  if (authDraft.codeSent) {
    showSentAnimation();
    $("emailCodeBlock").classList.remove("hidden");
  }
}

function validEmail(email) {
  return /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email);
}

function showSentAnimation() {
  const node = $("registerSent");
  node.classList.remove("hidden", "sent-pop");
  void node.offsetWidth;
  node.classList.add("sent-pop");
}

async function submitRegister() {
  const email = $("registerEmail").value.trim();

  if (!validEmail(email)) {
    $("registerError").textContent = "Введи корректную почту";
    $("registerError").classList.remove("hidden");
    $("registerSent").classList.add("hidden");
    return;
  }

  $("registerError").classList.add("hidden");
  $("emailCodeBlock").classList.add("hidden");
  await saveAuthDraft({ mode: "register", email, codeSent: false });
  setButtonState($("registerBtn"), "busy", "Отправка");

  try {
    await api("/auth/request-code", {
      method: "POST",
      body: JSON.stringify({ email }),
    });
    showSentAnimation();
    $("emailCodeBlock").classList.remove("hidden");
    $("emailCode").focus();
    await saveAuthDraft({ mode: "register", email, codeSent: true });
    finishButton($("registerBtn"), true, "Отправлено");
  } catch (error) {
    $("registerError").textContent = compactText(error);
    $("registerError").classList.remove("hidden");
    finishButton($("registerBtn"), false, "Ошибка");
  }
}

async function verifyEmailCode() {
  const email = $("registerEmail").value.trim();
  const code = $("emailCode").value.trim();

  if (!validEmail(email) || !code) {
    $("registerError").textContent = "Введи почту и код из письма";
    $("registerError").classList.remove("hidden");
    return;
  }

  $("registerError").classList.add("hidden");
  setButtonState($("verifyEmailCodeBtn"), "busy", "Проверка");

  try {
    const data = await api("/auth/verify-code", {
      method: "POST",
      body: JSON.stringify({ email, code }),
    });
    role = "user";
    userEmail = data.email || email.toLowerCase();
    await chrome.storage.session.set({ role, userEmail });
    await clearAuthDraft();
    finishButton($("verifyEmailCodeBtn"), true, "Готово");
    renderRole();
    checkStatus();
  } catch (error) {
    $("registerError").textContent = compactText(error);
    $("registerError").classList.remove("hidden");
    finishButton($("verifyEmailCodeBtn"), false, "Ошибка");
  }
}

async function loginByCode() {
  const code = $("accessCode").value.trim();
  const codes = await loadCodes();

  if (code === codes.admin_code) {
    role = "admin";
    userEmail = "";
  } else {
    $("loginError").textContent = "Неверный код доступа";
    $("loginError").classList.remove("hidden");
    return;
  }

  $("loginError").classList.add("hidden");
  await chrome.storage.session.set({ role, userEmail });
  await clearAuthDraft();
  renderRole();
  checkStatus();
}

async function logout() {
  role = "";
  userEmail = "";
  await chrome.storage.session.remove(["role", "userEmail"]);
  await clearAuthDraft();
  await chrome.storage.local.remove(["role"]);
  renderRole();
}

function renderRole() {
  const logged = role === "user" || role === "admin";
  $("loginView").classList.toggle("hidden", logged);
  $("mainView").classList.toggle("hidden", !logged);
  $("logoutBtn").classList.toggle("hidden", !logged);
  if (!logged) return;

  const admin = role === "admin";
  $("roleBadge").textContent = admin ? "admin" : "user";
  $("roleBadge").title = admin ? "admin" : userEmail;
  $("roleBadge").className = admin ? "badge admin" : "badge user";
  $("mgrTabBtn").classList.toggle("hidden", !admin);
  document.querySelector(".top-grid")?.classList.toggle("user-mode", !admin);
  document.querySelector(".api-card")?.classList.toggle("hidden", !admin);
  if (!admin) activateTab("chat");
  renderChatHistory();
}

async function api(path, options = {}) {
  const response = await fetch(`${apiUrl}${path}`, {
    ...options,
    headers: {
      "Content-Type": "application/json",
      ...(options.headers || {}),
    },
  });
  const text = await response.text();
  const data = text ? JSON.parse(text) : {};
  if (!response.ok) throw data;
  return data;
}

async function checkStatus(button = null) {
  setButtonState(button, "busy", "Check");
  try {
    const data = await api("/status");
    setApiState(data);
    writeOutput(data);
    finishButton(button, true, "OK");
  } catch (error) {
    setApiState(error, true);
    writeOutput(error);
    finishButton(button, false, "Error");
  }
}

async function refreshStatusBadge() {
  try {
    const data = await api("/status");
    setApiState(data);
  } catch (error) {
    setApiState(error, true);
  }
}

function addMessage(type, text) {
  const item = document.createElement("div");
  item.className = `message ${type}`;
  appendTextWithLinks(item, text);
  $("messages").appendChild(item);
  $("messages").scrollTop = $("messages").scrollHeight;
}

function clearMessages() {
  $("messages").textContent = "";
}

function renderChatHistory() {
  if (!role) return;
  clearMessages();
  const visibleLogs = (chatLogsByUser[currentHistoryKey()] || []).slice(-30);
  if (!visibleLogs.length) {
    addMessage("bot", "Задай вопрос по базе знаний.");
    return;
  }
  for (const item of visibleLogs) {
    if (item.question) addMessage("user", item.question);
    if (item.answer) addMessage("bot", item.answer);
  }
}

async function saveChatLog(question, answer) {
  const key = currentHistoryKey();
  const logs = Array.isArray(chatLogsByUser[key]) ? chatLogsByUser[key] : [];
  logs.push({ time: new Date().toISOString(), role, email: userEmail, question, answer });
  chatLogsByUser[key] = logs.slice(-200);
  await chrome.storage.local.set({ chatLogsByUser });
}

async function logChatToSheet(question, answer) {
  if (role !== "user" || !userEmail) return;

  try {
    await api("/dhb/log-chat", {
      method: "POST",
      body: JSON.stringify({ email: userEmail, question, answer }),
    });
  } catch (error) {
    console.warn("Google Sheets chat log failed", error);
  }
}


function openAskDebugModal() {
  if (role !== "admin") {
    writeOutput("Недостаточно прав");
    return;
  }

  const modal = $("askDebugModal");
  modal.classList.remove("hidden");
  modal.setAttribute("aria-hidden", "false");
  $("askDebugQuestion").value = "";
  setTimeout(() => $("askDebugQuestion").focus(), 40);
}

function closeAskDebugModal() {
  const modal = $("askDebugModal");
  modal.classList.add("hidden");
  modal.setAttribute("aria-hidden", "true");
  setButtonState($("askDebugRunBtn"), "idle");
}

async function runAskDebugFromModal() {
  if (role !== "admin") {
    writeOutput("Недостаточно прав");
    return;
  }

  const question = $("askDebugQuestion").value.trim();
  if (!question) {
    writeOutput("Введите вопрос для Ask Debug");
    $("askDebugQuestion").focus();
    return;
  }

  setButtonState($("askDebugRunBtn"), "busy", "Запрос");
  setButtonState($("askDebugBtn"), "busy", "Debug");
  writeOutput({
    action: "/ask_debug",
    status: "sending",
    request: { question },
    hint: "Ожидание ответа от сервера.",
  });

  try {
    const data = await api("/ask_debug", {
      method: "POST",
      body: JSON.stringify({ question }),
    });
    closeAskDebugModal();
    writeOutput(data);
    refreshStatusBadge();
    finishButton($("askDebugBtn"), true, "OK");
  } catch (error) {
    writeOutput(error);
    finishButton($("askDebugBtn"), false, "Error");
    finishButton($("askDebugRunBtn"), false, "Ошибка");
  }
}

async function ask(debug = false, button = $("askBtn")) {
  const question = $("question").value.trim();
  if (!question) return;

  addMessage("user", question);
  $("question").value = "";
  setLoading(button, true, debug ? "Debug" : "Ask...");

  try {
    const data = await api(debug ? "/ask_debug" : "/ask", {
      method: "POST",
      body: JSON.stringify({ question }),
    });
    const answer = data.answer || JSON.stringify(data);
    addMessage("bot", answer);
    writeOutput(data);
    await saveChatLog(question, answer);
    await logChatToSheet(question, answer);
  } catch (error) {
    addMessage("error", compactText(error));
    writeOutput(error);
  } finally {
    setLoading(button, false);
  }
}

async function run(button, path, body = {}) {
  if (role !== "admin") {
    writeOutput("Недостаточно прав");
    return;
  }
  setButtonState(button, "busy", "Start");
  writeOutput({
    action: path,
    status: "sending",
    request: body,
    hint: "Button clicked. Waiting for server response.",
  });
  try {
    const data = await api(path, {
      method: "POST",
      body: JSON.stringify(body),
    });
    writeOutput({
      action: path,
      request: body,
      response: data,
      hint: "Запрос принят сервером. Смотри API status сверху или нажми Status.",
    });
    refreshStatusBadge();
    setTimeout(checkStatus, 1000);
    setTimeout(refreshStatusBadge, 5000);
    finishButton(button, true, "Started");
  } catch (error) {
    writeOutput(error);
    finishButton(button, false, "Error");
  } finally {
    if (button.disabled) button.disabled = false;
  }
}

function fileRequest() {
  const type = $("sourceFileType").value;
  const limit = Number($("sourceLimit").value);
  const body = {
    max_sources: limit > 0 ? limit : null,
    force: $("forceRefresh").checked,
  };

  if (type === "docs") {
    body.registry_path = $("sourceFilePath").value || "xdt/rpo/docs_registry.json";
    return { path: "/parse/docs-registry", body };
  }

  body.package_list_path = $("sourceFilePath").value || "xdt/rpo/packages.txt";
  return { path: "/parse/packages", body };
}

function activateTab(name) {
  document.querySelectorAll(".tab").forEach((item) => item.classList.remove("active"));
  document.querySelectorAll(".tab-panel").forEach((item) => item.classList.remove("active"));
  document.querySelector(`.tab[data-tab="${name}"]`)?.classList.add("active");
  $(`${name}Tab`).classList.add("active");
}

function bindEvents() {
  $("showLoginBtn").onclick = () => {
    setAuthMode("login");
    saveAuthDraft({ mode: "login" });
  };
  $("showRegisterBtn").onclick = () => {
    setAuthMode("register");
    saveAuthDraft({ mode: "register", email: $("registerEmail").value.trim() });
  };
  $("registerBtn").onclick = () => submitRegister();
  $("verifyEmailCodeBtn").onclick = () => verifyEmailCode();
  $("codeLoginBtn").onclick = () => loginByCode();
  $("logoutBtn").onclick = () => logout();
  $("saveApiBtn").onclick = () => {
    saveSettings();
    finishButton($("saveApiBtn"), true, "Saved");
  };
  $("statusBtn").onclick = () => checkStatus($("statusBtn"));
  $("mgrStatusBtn").onclick = () => checkStatus($("mgrStatusBtn"));
  $("askBtn").onclick = () => ask(false, $("askBtn"));
  $("askDebugBtn").onclick = () => openAskDebugModal();
  $("rebuildBtn").onclick = () => run($("rebuildBtn"), "/rebuild");
  $("parseUrlBtn").onclick = () => run($("parseUrlBtn"), "/parse/url", { url: $("singleUrl").value });
  $("parseFileBtn").onclick = () => {
    const request = fileRequest();
    run($("parseFileBtn"), request.path, request.body);
  };
  $("sourceLimit").onkeydown = (event) => {
    if (event.key === "Enter") {
      const request = fileRequest();
      run($("parseFileBtn"), request.path, request.body);
    }
  };
  $("sourceLimit").onchange = () => {
    const request = fileRequest();
    writeOutput({
      preview: true,
      path: request.path,
      request: request.body,
      hint: "N выбран. Нажми Parse file или Enter, чтобы запустить.",
    });
  };
  $("sourceFilePath").onkeydown = (event) => {
    if (event.key === "Enter") {
      const request = fileRequest();
      run($("parseFileBtn"), request.path, request.body);
    }
  };
  $("sourceFileType").onchange = () => {
    $("sourceFilePath").value =
      $("sourceFileType").value === "docs" ? "xdt/rpo/docs_registry.json" : "xdt/rpo/packages.txt";
  };

  $("askDebugCloseBtn").onclick = () => closeAskDebugModal();
  $("askDebugCancelBtn").onclick = () => closeAskDebugModal();
  $("askDebugBackdrop").onclick = () => closeAskDebugModal();
  $("askDebugRunBtn").onclick = () => runAskDebugFromModal();
  $("askDebugQuestion").onkeydown = (event) => {
    if (event.key === "Enter" && (event.ctrlKey || event.metaKey)) runAskDebugFromModal();
  };
  $("clearLogBtn").onclick = () => writeOutput("");
  document.querySelectorAll('input[name="outputMode"]').forEach((item) => {
    item.onchange = () => writeOutput(lastOutput);
  });
  document.querySelectorAll(".tab").forEach((button) => {
    button.onclick = () => {
      if (button.dataset.tab === "mgr" && role !== "admin") return;
      activateTab(button.dataset.tab);
    };
  });
  $("question").onkeydown = (event) => {
    if (event.key === "Enter" && (event.ctrlKey || event.metaKey)) ask(false);
  };
  $("accessCode").onkeydown = (event) => {
    if (event.key === "Enter") loginByCode();
  };
  $("registerEmail").onkeydown = (event) => {
    if (event.key === "Enter") submitRegister();
  };
  $("registerEmail").oninput = () => {
    if (!$("registerForm").classList.contains("hidden")) {
      saveAuthDraft({ mode: "register", email: $("registerEmail").value.trim() });
    }
  };
  $("emailCode").onkeydown = (event) => {
    if (event.key === "Enter") verifyEmailCode();
  };
  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape" && !$("askDebugModal").classList.contains("hidden")) {
      closeAskDebugModal();
    }
  });
}

loadSettings().then(() => {
  bindEvents();
  if (role) checkStatus();
});
