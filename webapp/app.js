/* Telegram Mini App — запись в салон. Данные держим синхронно с config.py. */
const tg = (window.Telegram && window.Telegram.WebApp) ? window.Telegram.WebApp : null;
const inTelegram = !!(tg && tg.initData !== "");
if (tg) { tg.ready(); tg.expand(); }
// Класс tg-mode (прячет запасную кнопку, используем нативную MainButton) —
// только в РЕАЛЬНОМ Telegram. SDK создаёт window.Telegram.WebApp и в браузере,
// поэтому ориентируемся на initData, а не на наличие объекта.
if (inTelegram) document.body.classList.add("tg-mode");

// --- Данные (зеркало config.py) ---
const SERVICES = [
  { id: "haircut_m", name: "Мужская стрижка", price: 25, dur: 60 },
  { id: "haircut_w", name: "Женская стрижка", price: 40, dur: 90 },
  { id: "color", name: "Окрашивание", price: 90, dur: 120 },
  { id: "manicure", name: "Маникюр с покрытием", price: 35, dur: 90 },
  { id: "brows", name: "Коррекция и окрашивание бровей", price: 20, dur: 30 },
];
const MASTERS = {
  anna: { name: "Анна", emoji: "💇‍♀️" },
  ivan: { name: "Иван", emoji: "💈" },
  lena: { name: "Лена", emoji: "💅" },
};
const SERVICE_MASTERS = {
  haircut_m: ["ivan"], haircut_w: ["anna", "lena"], color: ["anna"],
  manicure: ["lena"], brows: ["anna", "lena"],
};
const ENABLE_MASTERS = true;
const WORK_START = 10, WORK_END = 20, SLOT_MIN = 60, DAYS_AHEAD = 7;
const WORK_DAYS = [1, 2, 3, 4, 5, 6];               // 0=Вс..6=Сб → Пн–Сб
const CURRENCY = "BYN";
const WD = ["Вс", "Пн", "Вт", "Ср", "Чт", "Пт", "Сб"];
const MO = ["янв", "фев", "мар", "апр", "май", "июн", "июл", "авг", "сен", "окт", "ноя", "дек"];

const state = { service: null, master: null, date: null, time: null, step: "service" };
const $ = (id) => document.getElementById(id);
const haptic = (t) => { if (tg) tg.HapticFeedback.selectionChanged(); };

function mastersFor(sid) { return SERVICE_MASTERS[sid] || Object.keys(MASTERS); }
function needsMaster(sid) { return ENABLE_MASTERS && mastersFor(sid).length > 1; }

// --- Рендер шагов ---
function renderServices() {
  $("services").innerHTML = "";
  SERVICES.forEach((s) => {
    const el = document.createElement("div");
    el.className = "item" + (state.service === s.id ? " sel" : "");
    el.innerHTML = `<div><div class="item__name">${s.name}</div>
      <div class="item__meta">~${s.dur} мин</div></div>
      <div class="item__price">${s.price} ${CURRENCY}</div>`;
    el.onclick = () => {
      state.service = s.id; state.master = null; state.time = null; haptic();
      if (needsMaster(s.id)) { renderMasters(); show("master"); }
      else { state.master = ENABLE_MASTERS ? mastersFor(s.id)[0] : null; renderDates(); show("when"); }
    };
    $("services").appendChild(el);
  });
}

function renderMasters() {
  const box = $("masters"); box.innerHTML = "";
  const add = (id, label, emoji) => {
    const el = document.createElement("div");
    el.className = "item" + (state.master === id ? " sel" : "");
    el.innerHTML = `<div class="item__name">${emoji} ${label}</div>`;
    el.onclick = () => { state.master = id; haptic(); renderDates(); show("when"); };
    box.appendChild(el);
  };
  mastersFor(state.service).forEach((mid) => add(mid, MASTERS[mid].name, MASTERS[mid].emoji));
  add("any", "Любой мастер", "🙋");
}

function workDates() {
  const out = []; const d = new Date(); d.setHours(0, 0, 0, 0);
  for (let i = 0; out.length < DAYS_AHEAD && i < DAYS_AHEAD * 3; i++) {
    if (WORK_DAYS.includes(d.getDay())) out.push(new Date(d));
    d.setDate(d.getDate() + 1);
  }
  return out;
}
function isoDate(d) {
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
}

function renderDates() {
  const box = $("dates"); box.innerHTML = "";
  workDates().forEach((d) => {
    const iso = isoDate(d);
    const el = document.createElement("div");
    el.className = "chip" + (state.date === iso ? " sel" : "");
    el.innerHTML = `<div class="chip__d">${d.getDate()}</div>
      <div class="chip__m">${MO[d.getMonth()]} · ${WD[d.getDay()]}</div>`;
    el.onclick = () => { state.date = iso; state.time = null; haptic(); renderDates(); renderTimes(); updateMain(); };
    box.appendChild(el);
  });
  renderTimes();
}

function renderTimes() {
  const box = $("times"); box.innerHTML = "";
  if (!state.date) { box.innerHTML = `<div class="item__meta">Выберите день ↑</div>`; return; }
  for (let h = WORK_START; h < WORK_END; h += SLOT_MIN / 60) {
    const label = `${String(h).padStart(2, "0")}:00`;
    const el = document.createElement("div");
    el.className = "slot" + (state.time === label ? " sel" : "");
    el.textContent = label;
    el.onclick = () => { state.time = label; haptic(); renderTimes(); updateMain(); };
    box.appendChild(el);
  }
}

function renderContact() {
  if (tg && tg.initDataUnsafe && tg.initDataUnsafe.user && !$("name").value) {
    $("name").value = tg.initDataUnsafe.user.first_name || "";
  }
  const s = SERVICES.find((x) => x.id === state.service) || {};
  const mLabel = state.master && state.master !== "any" ? MASTERS[state.master].name : "Любой";
  const d = state.date ? state.date.split("-").reverse().join(".") : "";
  $("summary").innerHTML =
    `💇 <b>${s.name || ""}</b><br>👩‍🔧 Мастер: <b>${mLabel}</b><br>
     🗓 <b>${d} в ${state.time || ""}</b><br>💰 <b>${s.price || ""} ${CURRENCY}</b>`;
}

// --- Навигация / главная кнопка ---
const STEPS = { service: 1, master: 2, when: 3, contact: 4 };
const HINTS = {
  service: "Шаг 1 из 4 · выберите услугу",
  master: "Шаг 2 из 4 · выберите мастера",
  when: "Шаг 3 из 4 · дата и время",
  contact: "Шаг 4 из 4 · контакты",
};
function show(step) {
  state.step = step;
  ["service", "master", "when", "contact"].forEach((s) =>
    $("step-" + s).classList.toggle("hidden", s !== step));
  $("stepHint").textContent = HINTS[step];
  $("bar").style.width = (STEPS[step] * 25) + "%";
  if (step === "contact") renderContact();
  updateMain();
}

function updateMain() {
  let label = "Далее", enabled = false;
  if (state.step === "when") { label = "Далее"; enabled = !!(state.date && state.time); }
  else if (state.step === "contact") { label = "Записаться 🎉"; enabled = true; }
  else { enabled = false; }
  const visible = state.step === "when" || state.step === "contact";

  if (inTelegram) {
    if (visible) { tg.MainButton.setText(label); tg.MainButton.show();
      enabled ? tg.MainButton.enable() : tg.MainButton.disable(); }
    else tg.MainButton.hide();
  } else {
    const b = $("fallbackBtn");
    b.style.display = visible ? "block" : "none";
    b.textContent = label; b.disabled = !enabled;
  }
}

function onMain() {
  if (state.step === "when") { if (state.date && state.time) show("contact"); return; }
  if (state.step === "contact") submit();
}

function submit() {
  const name = $("name").value.trim();
  const phone = $("phone").value.trim();
  if (!name) return alertMsg("Введите имя");
  if (phone.replace(/\D/g, "").length < 7) return alertMsg("Введите телефон");
  const payload = {
    service: state.service,
    master: state.master || "any",
    date: state.date, time: state.time,
    name, phone,
  };
  if (inTelegram) { tg.HapticFeedback.notificationOccurred("success"); tg.sendData(JSON.stringify(payload)); }
  else alertMsg("Демо вне Telegram. Отправлено бы:\n" + JSON.stringify(payload, null, 2));
}
function alertMsg(m) { if (tg) tg.showAlert ? tg.showAlert(m) : alert(m); else alert(m); }

if (tg) tg.MainButton.onClick(onMain);
$("fallbackBtn").addEventListener("click", onMain);

renderServices();
show("service");
