const dateEl = document.getElementById("date");
const dayEl = document.getElementById("dayNumber");
const card = document.getElementById("holidayCard");
const toast = document.getElementById("toast");
const root = document.documentElement;

let animationTimeout;
let toastTimeout;
let currentHoliday = null;

function getCsrfToken() {
  const metaToken = document.querySelector('meta[name="csrf-token"]')?.getAttribute("content");
  if (metaToken) return metaToken;
  if (typeof window.CSRF_TOKEN === "string" && window.CSRF_TOKEN) return window.CSRF_TOKEN;
  return "";
}

function showHoliday(item) {
  clearTimeout(animationTimeout);

  currentHoliday = item;
  updateFavoriteButtonUI();
  syncLikeButtonAvailability();

  card.classList.add("loading");

  animationTimeout = setTimeout(() => {
    document.getElementById("holidayTitle").classList.remove("skeleton-text");
    document.getElementById("holidayDescription").classList.remove("skeleton-text");
    document.getElementById("holidayTag").classList.remove("skeleton-text");
    document.getElementById("holidayType").classList.remove("skeleton-text");
    document.getElementById("dayNumber").classList.remove("skeleton-text");
    document.getElementById("holidayEmoji").classList.remove("skeleton-box");
    document.getElementById("holidayMission").classList.remove("skeleton-text");

    document.getElementById("holidayTitle").textContent = item.title || "";
    document.getElementById("holidayEmoji").textContent = item.emoji || "🎉";
    document.getElementById("holidayDescription").textContent = item.description || "";
    document.getElementById("holidayMission").textContent = item.mission || "";

    if (item.tint) {
      root.style.setProperty("--tint", item.tint);
      card.style.setProperty("--tint", item.tint);
    }

    const dayLabel = String(item.day_number ?? "");
    document.getElementById("holidayTag").textContent = dayLabel.includes("СЛУЧАЙНЫЙ")
      ? "СЛУЧАЙНЫЙ ПРАЗДНИК"
      : "ПРАЗДНИК ДНЯ";
    dayEl.textContent = dayLabel;

    const typeEl = document.getElementById("holidayType");
    const typeMap = {
      official: { label: "📅 ОФИЦИАЛЬНЫЙ", cls: "type-official" },
      unusual: { label: "🎈 НЕОБЫЧНЫЙ", cls: "type-unusual" },
      author: { label: "✍️ АВТОРСКИЙ", cls: "type-author" },
    };
    const t = typeMap[item.type] || typeMap.author;
    typeEl.textContent = t.label;
    typeEl.className = "type-badge " + t.cls;

    const factWrap = document.getElementById("holidayFactWrap");
    const factEl = document.getElementById("holidayFact");
    if (item.fact && item.fact.trim().length > 0) {
      factEl.textContent = item.fact;
      factWrap.classList.remove("hidden");
    } else {
      factWrap.classList.add("hidden");
    }

    const ogImageTag = document.getElementById("ogImage");
    if (ogImageTag && item.image_url) {
      const absoluteUrl = window.location.origin + item.image_url;
      ogImageTag.setAttribute("content", absoluteUrl);
    }

    card.classList.remove("loading");

    loadLikesForCurrentHoliday();
  }, 300);
}

function triggerConfetti() {
  if (typeof confetti === "function") {
    confetti({
      particleCount: 120,
      spread: 80,
      origin: { y: 0.6 },
      colors: ["#f8dfe3", "#b66d7b", "#e1eee4", "#f7edc9", "#ebe5f6"],
    });
  }
}

async function loadToday() {
  try {
    const response = await fetch("/api/today");
    if (!response.ok) throw new Error("Ошибка загрузки");
    const data = await response.json();

    showHoliday(data);

    const now = new Date();
    const dateText = new Intl.DateTimeFormat("ru-RU", {
      day: "numeric",
      month: "long",
      year: "numeric",
    }).format(now);
    if (dateEl) dateEl.textContent = dateText;
  } catch (error) {
    console.error("Ошибка:", error);
    if (dateEl) dateEl.textContent = "не удалось загрузить дату";
  }
}

async function loadYesterday() {
  try {
    const response = await fetch("/api/yesterday");
    if (!response.ok) throw new Error("Ошибка загрузки");
    const data = await response.json();
    showHoliday(data);
  } catch (error) {
    console.error("Ошибка:", error);
  }
}

async function loadRandom() {
  try {
    const lastId = localStorage.getItem("lastRandomHolidayId") || "";
    const query = /^\d+$/.test(lastId) ? `?exclude=${encodeURIComponent(lastId)}` : "";
    const response = await fetch(`/api/random${query}`);
    if (!response.ok) throw new Error("Ошибка загрузки");
    const data = await response.json();

    if (data.id !== undefined && data.id !== null) {
      localStorage.setItem("lastRandomHolidayId", String(data.id));
    }

    showHoliday(data);
    triggerConfetti();
  } catch (error) {
    console.error("Ошибка:", error);
  }
}

async function loadDailyMessage() {
  try {
    const response = await fetch("/api/message");
    if (!response.ok) return;
    const data = await response.json();

    const wrap = document.getElementById("dailyMessageWrap");
    const textEl = document.getElementById("dailyMessageText");

    if (data.text && wrap && textEl) {
      textEl.textContent = data.text;
      wrap.classList.remove("hidden");
    }
  } catch (err) {
    console.error("Ошибка загрузки послания:", err);
  }
}

function getFavorites() {
  try {
    const parsed = JSON.parse(localStorage.getItem("holidayFavorites"));
    return Array.isArray(parsed) ? parsed : [];
  } catch (_) {
    return [];
  }
}

function updateFavCount() {
  const favs = getFavorites();
  const countEl = document.getElementById("favCount");
  if (countEl) countEl.textContent = String(favs.length);
}

function isFavorite(id) {
  const favs = getFavorites();
  return favs.some((item) => item.id === id);
}

function updateFavoriteButtonUI() {
  const btn = document.getElementById("favoriteBtn");
  if (!btn || !currentHoliday) return;

  const active = isFavorite(currentHoliday.id);
  btn.textContent = "⭐ В избранное";
  btn.setAttribute("aria-pressed", active ? "true" : "false");
  if (active) {
    btn.style.background = "var(--pink-deep)";
    btn.style.color = "white";
  } else {
    btn.style.background = "";
    btn.style.color = "";
  }
}

const favoriteBtn = document.getElementById("favoriteBtn");
if (favoriteBtn) {
  favoriteBtn.addEventListener("click", () => {
    if (!currentHoliday) return;

    let favs = getFavorites();
    const index = favs.findIndex((item) => item.id === currentHoliday.id);

    if (index > -1) {
      favs.splice(index, 1);
    } else {
      favs.push(currentHoliday);
    }

    localStorage.setItem("holidayFavorites", JSON.stringify(favs));
    updateFavCount();
    updateFavoriteButtonUI();
  });
}

const modal = document.getElementById("favoritesModal");
const openFavoritesBtn = document.getElementById("openFavorites");
const closeFavoritesBtn = document.getElementById("closeFavorites");

if (openFavoritesBtn && modal) {
  openFavoritesBtn.addEventListener("click", () => {
    renderFavoritesList();
    modal.classList.add("show");
  });
}

if (closeFavoritesBtn && modal) {
  closeFavoritesBtn.addEventListener("click", () => {
    modal.classList.remove("show");
  });
}

if (modal) {
  modal.addEventListener("click", (e) => {
    if (e.target === modal) modal.classList.remove("show");
  });
}

function renderFavoritesList() {
  const listEl = document.getElementById("favoritesList");
  if (!listEl) return;
  const favs = getFavorites();

  listEl.replaceChildren();

  if (favs.length === 0) {
    const emptyP = document.createElement("p");
    emptyP.className = "empty-fav";
    emptyP.append("У тебя пока нет сохранённых праздников.");
    emptyP.appendChild(document.createElement("br"));
    emptyP.append("Нажми «⭐ В избранное» на любом празднике!");
    listEl.appendChild(emptyP);
    return;
  }

  favs.forEach((item) => {
    const row = document.createElement("div");
    row.className = "fav-item";

    const info = document.createElement("div");
    info.className = "fav-info";
    info.addEventListener("click", () => loadFavoriteItem(item.id));

    const emojiSpan = document.createElement("span");
    emojiSpan.className = "fav-emoji";
    emojiSpan.textContent = item.emoji || "🎉";

    const titleSpan = document.createElement("span");
    titleSpan.className = "fav-title";
    titleSpan.textContent = item.title || "";

    info.appendChild(emojiSpan);
    info.appendChild(titleSpan);

    const delBtn = document.createElement("button");
    delBtn.type = "button";
    delBtn.className = "fav-delete";
    delBtn.title = "Удалить";
    delBtn.textContent = "🗑️";
    delBtn.addEventListener("click", (event) => removeFavorite(item.id, event));

    row.appendChild(info);
    row.appendChild(delBtn);
    listEl.appendChild(row);
  });
}

function loadFavoriteItem(id) {
  const favs = getFavorites();
  const item = favs.find((f) => f.id === id);
  if (item) {
    showHoliday(item);
    if (modal) modal.classList.remove("show");
  }
}

function removeFavorite(id, event) {
  if (event) event.stopPropagation();
  let favs = getFavorites();
  favs = favs.filter((item) => item.id !== id);
  localStorage.setItem("holidayFavorites", JSON.stringify(favs));
  updateFavCount();
  updateFavoriteButtonUI();
  renderFavoritesList();
}

async function shareHoliday() {
  const title = document.getElementById("holidayTitle")?.textContent?.trim() || "праздник";
  const text = `Сегодня — ${title}! А у тебя какой праздник?`;
  const url = window.location.href;
  const sharePayload = `${text} ${url}`;

  const isMobile = navigator.maxTouchPoints > 0 && /Android|iPhone|iPad|iPod/i.test(navigator.userAgent);

  if (isMobile && typeof navigator.share === "function") {
    try {
      await navigator.share({ title: "сегодня", text: text, url: url });
      return;
    } catch (err) {
      if (err && err.name === "AbortError") return;
    }
  }

  try {
    if (navigator.clipboard && window.isSecureContext) {
      await navigator.clipboard.writeText(sharePayload);
      showToast();
      return;
    }
  } catch (_) {}

  try {
    const textArea = document.createElement("textarea");
    textArea.value = sharePayload;
    textArea.style.position = "fixed";
    textArea.style.opacity = "0";
    document.body.appendChild(textArea);
    textArea.focus();
    textArea.select();
    const successful = document.execCommand("copy");
    document.body.removeChild(textArea);
    if (successful) {
      showToast();
      return;
    }
  } catch (_) {}

  showToast("Не удалось скопировать ссылку.");
}

function showToast(message = "Ссылка скопирована!") {
  if (!toast) return;
  clearTimeout(toastTimeout);
  toast.textContent = message;
  toast.classList.add("show");
  toastTimeout = setTimeout(() => {
    toast.classList.remove("show");
  }, 2500);
}

function updateStreak() {
  const streakContainer = document.getElementById("streak-container");
  if (!streakContainer) return;

  const today = new Date().toDateString();

  const lastVisit = localStorage.getItem("lastVisitDate");
  let streak = parseInt(localStorage.getItem("streakCount"), 10) || 0;

  if (lastVisit !== today) {
    const yesterday = new Date();
    yesterday.setDate(yesterday.getDate() - 1);

    if (lastVisit === yesterday.toDateString()) {
      streak++;
    } else {
      streak = 1;
    }
    localStorage.setItem("lastVisitDate", today);
    localStorage.setItem("streakCount", String(streak));
  }

  if (streak > 0) {
    streakContainer.classList.remove("hidden");
    streakContainer.style.display = "block";
    const word = streak === 1 ? "день" : streak < 5 ? "дня" : "дней";
    streakContainer.textContent = `🔥 ${streak} ${word}`;
  }
}

function getVoterHash() {
  let hash = localStorage.getItem("voterHash");
  if (!hash) {
    const randomPart =
      typeof crypto !== "undefined" && typeof crypto.randomUUID === "function"
        ? crypto.randomUUID()
        : Math.random().toString(36).substring(2) + Date.now().toString(36);
    hash = "user_" + randomPart;
    localStorage.setItem("voterHash", hash);
  }
  return hash;
}

function syncLikeButtonAvailability() {
  const likeBtn = document.getElementById("likeBtn");
  if (!likeBtn) return;
  const isPromo = currentHoliday && Number(currentHoliday.id) < 0;
  likeBtn.disabled = Boolean(isPromo);
  likeBtn.title = isPromo ? "Лайки для спецвыпуска недоступны" : "";
}

async function loadLikesForCurrentHoliday() {
  if (!currentHoliday) return;

  const likeCountEl = document.getElementById("likeCount");
  const likeBtn = document.getElementById("likeBtn");
  if (!likeCountEl || !likeBtn) return;

  try {
    const res = await fetch(`/api/likes/${currentHoliday.id}`);
    if (res.ok) {
      const data = await res.json();
      likeCountEl.textContent = String(data.likes ?? 0);
    }

    const likedIds = JSON.parse(localStorage.getItem("likedHolidayIds")) || [];
    const isLiked = Array.isArray(likedIds) && likedIds.includes(currentHoliday.id);
    likeBtn.classList.toggle("liked", isLiked);
    likeBtn.setAttribute("aria-pressed", isLiked ? "true" : "false");
  } catch (err) {
    console.error("Ошибка загрузки лайков:", err);
  }
}

const likeBtnEl = document.getElementById("likeBtn");
if (likeBtnEl) {
  likeBtnEl.addEventListener("click", async () => {
    if (!currentHoliday) return;
    if (Number(currentHoliday.id) < 0) {
      showToast("Лайки для спецвыпуска недоступны");
      return;
    }

    const likeBtn = document.getElementById("likeBtn");
    const likeCountEl = document.getElementById("likeCount");
    const voterHash = getVoterHash();
    const csrfToken = getCsrfToken();

    const headers = { "Content-Type": "application/json" };
    if (csrfToken) {
      headers["X-CSRF-Token"] = csrfToken;
    }

    try {
      const response = await fetch(`/api/like/${currentHoliday.id}`, {
        method: "POST",
        headers,
        body: JSON.stringify({ voter_hash: voterHash }),
      });

      if (response.ok) {
        const data = await response.json();
        if (likeCountEl) likeCountEl.textContent = String(data.likes ?? 0);

        let likedIds = JSON.parse(localStorage.getItem("likedHolidayIds"));
        if (!Array.isArray(likedIds)) likedIds = [];

        if (data.liked) {
          likeBtn?.classList.add("liked");
          likeBtn?.setAttribute("aria-pressed", "true");
          if (!likedIds.includes(currentHoliday.id)) likedIds.push(currentHoliday.id);
        } else {
          likeBtn?.classList.remove("liked");
          likeBtn?.setAttribute("aria-pressed", "false");
          likedIds = likedIds.filter((id) => id !== currentHoliday.id);
        }
        localStorage.setItem("likedHolidayIds", JSON.stringify(likedIds));
      } else {
        const errData = await response.json().catch(() => ({}));
        console.error("Ошибка лайка:", response.status, errData.error || "");
      }
    } catch (err) {
      console.error("Ошибка отправки лайка:", err);
    }
  });
}

const surpriseBtn = document.getElementById("surpriseButton");
if (surpriseBtn) surpriseBtn.addEventListener("click", loadRandom);

const todayBtn = document.getElementById("todayButton");
if (todayBtn) todayBtn.addEventListener("click", loadToday);

const yesterdayBtn = document.getElementById("yesterdayButton");
if (yesterdayBtn) yesterdayBtn.addEventListener("click", loadYesterday);

const shareBtn = document.getElementById("shareButton");
if (shareBtn) shareBtn.addEventListener("click", shareHoliday);

loadToday();
updateStreak();
loadDailyMessage();
updateFavCount();