const dateEl = document.getElementById("date");
const dayEl = document.getElementById("dayNumber");
const card = document.getElementById("holidayCard");
const toast = document.getElementById("toast");
const themeToggle = document.getElementById("themeToggle");
const root = document.documentElement; // Корень HTML для смены темы

let animationTimeout; 

// ==========================================
// 1. ЛОГИКА ТЕМЫ (Автоопределение + Переключатель)
// ==========================================
function setTheme(theme) {
  root.setAttribute('data-theme', theme);
}

// Проверяем сохраненную тему или системные настройки телефона/ПК
const savedTheme = localStorage.getItem('theme');
const systemPrefersDark = window.matchMedia('(prefers-color-scheme: dark)').matches;
const initialTheme = savedTheme || (systemPrefersDark ? 'dark' : 'light');
setTheme(initialTheme);

// Слушаем клик по кнопке
themeToggle.addEventListener('click', () => {
  const currentTheme = root.getAttribute('data-theme');
  setTheme(currentTheme === 'dark' ? 'light' : 'dark');
});

// Слушаем изменение системной темы (если пользователь не выбрал вручную)
window.matchMedia('(prefers-color-scheme: dark)').addEventListener('change', e => {
  if (!localStorage.getItem('theme')) {
    setTheme(e.matches ? 'dark' : 'light');
  }
});


// ==========================================
// 2. ЛОГИКА ПРАЗДНИКОВ И СКЕЛЕТОНА
// ==========================================
function showHoliday(item) {
  clearTimeout(animationTimeout);
  
  // Включаем затухание
  card.classList.add("loading");

  animationTimeout = setTimeout(() => {
    // Убираем классы скелетона, чтобы появился текст
    document.getElementById("holidayTitle").classList.remove("skeleton-text");
    document.getElementById("holidayDescription").classList.remove("skeleton-text");
    document.getElementById("holidayTag").classList.remove("skeleton-text");
    document.getElementById("dayNumber").classList.remove("skeleton-text");
    document.getElementById("holidayEmoji").classList.remove("skeleton-box");
    document.getElementById("holidayMission").classList.remove("skeleton-text");

    // Вставляем данные
    document.getElementById("holidayTitle").textContent = item.title;
    document.getElementById("holidayEmoji").textContent = item.emoji;
    document.getElementById("holidayDescription").textContent = item.description;
    document.getElementById("holidayMission").textContent = item.mission;
    
    // 🌈 МЕНЯЕМ ДИНАМИЧЕСКИЙ ЦВЕТ ФОНА (всего сайта и карточки)
    root.style.setProperty("--tint", item.tint);
    card.style.setProperty("--tint", item.tint);
    
    document.getElementById("holidayTag").textContent = item.day_number.includes("СЛУЧАЙНЫЙ") ? "СЛУЧАЙНЫЙ ПРАЗДНИК" : "ПРАЗДНИК ДНЯ";
    dayEl.textContent = item.day_number;

    // Убираем затухание
    card.classList.remove("loading");
  }, 300);
}

// 🎉 Конфетти
function triggerConfetti() {
  if (typeof confetti === "function") {
    confetti({ particleCount: 120, spread: 80, origin: { y: 0.6 }, colors: ['#f8dfe3', '#b66d7b', '#e1eee4', '#f7edc9', '#ebe5f6'] });
  }
}

// Загрузка сегодняшнего праздника
async function loadToday() {
  try {
    const response = await fetch('/api/today');
    if (!response.ok) throw new Error('Ошибка загрузки');
    const data = await response.json();
    
    showHoliday(data);
    
    const now = new Date();
    const dateText = new Intl.DateTimeFormat("ru-RU", {
      day: "numeric", month: "long", year: "numeric"
    }).format(now);
    dateEl.textContent = dateText;
  } catch (error) {
    console.error('Ошибка:', error);
    dateEl.textContent = "не удалось загрузить дату";
  }
}

// 🕰 Загрузка вчерашнего праздника
async function loadYesterday() {
  try {
    const response = await fetch('/api/yesterday');
    if (!response.ok) throw new Error('Ошибка загрузки');
    const data = await response.json();
    showHoliday(data);
  } catch (error) {
    console.error('Ошибка:', error);
  }
}

// Загрузка случайного праздника
async function loadRandom() {
  try {
    const response = await fetch('/api/random');
    if (!response.ok) throw new Error('Ошибка загрузки');
    const data = await response.json();
    showHoliday(data);
    triggerConfetti();
  } catch (error) {
    console.error('Ошибка:', error);
  }
}

// 📤 Умная функция "Поделиться"
async function shareHoliday() {
  const title = document.getElementById("holidayTitle").textContent;
  const text = `Сегодня — ${title}! А у тебя какой праздник?`;
  const url = window.location.href;

  if (navigator.share) {
    try {
      await navigator.share({ title: 'сегодня 🎉', text: text, url: url });
      return;
    } catch (err) {}
  }

  try {
    const textArea = document.createElement("textarea");
    textArea.value = `${text} ${url}`;
    textArea.style.position = "fixed"; textArea.style.opacity = "0";
    document.body.appendChild(textArea);
    textArea.focus(); textArea.select();
    const successful = document.execCommand('copy');
    document.body.removeChild(textArea);
    if (successful) showToast();
  } catch (err) {
    alert('Не удалось скопировать ссылку.');
  }
}

function showToast() {
  toast.classList.add("show");
  setTimeout(() => { toast.classList.remove("show"); }, 2500);
}

// 🔥 ЛОГИКА СТРИКА (Счетчик дней подряд)
function updateStreak() {
  const streakContainer = document.getElementById('streak-container');
  const today = new Date().toDateString(); // Например: "Mon Nov 16 2026"
  
  let lastVisit = localStorage.getItem('lastVisitDate');
  let streak = parseInt(localStorage.getItem('streakCount')) || 0;

  if (lastVisit === today) {
    // Зашел сегодня повторно, ничего не меняем
  } else {
    const yesterday = new Date();
    yesterday.setDate(yesterday.getDate() - 1);
    
    if (lastVisit === yesterday.toDateString()) {
      // Зашел вчера и сегодня — увеличиваем стрик
      streak++;
    } else {
      // Пропустил день или зашел впервые — сбрасываем на 1
      streak = 1;
    }
    localStorage.setItem('lastVisitDate', today);
    localStorage.setItem('streakCount', streak);
  }

  if (streak > 0) {
    streakContainer.style.display = 'block';
    streakContainer.innerHTML = `🔥 ${streak} ${streak === 1 ? 'день' : (streak < 5 ? 'дня' : 'дней')}`;
  }
}

// Навешиваем обработчики
document.getElementById("surpriseButton").addEventListener("click", loadRandom);
document.getElementById("todayButton").addEventListener("click", loadToday);
document.getElementById("yesterdayButton").addEventListener("click", loadYesterday);
document.getElementById("shareButton").addEventListener("click", shareHoliday);

// Запускаем при открытии
loadToday();
updateStreak();