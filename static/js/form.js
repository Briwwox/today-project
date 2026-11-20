document.addEventListener('DOMContentLoaded', () => {
  const datePicker = document.getElementById('datePicker');
  const showDateInput = document.getElementById('showDateInput');
  const clearDateBtn = document.getElementById('clearDateBtn');

  if (!datePicker || !showDateInput || !clearDateBtn) return;

  const isValidMonthDay = (mmdd) => {
    if (!/^\d{2}-\d{2}$/.test(mmdd)) return false;
    const [monthStr, dayStr] = mmdd.split('-');
    const month = Number(monthStr);
    const day = Number(dayStr);
    if (month < 1 || month > 12 || day < 1 || day > 31) return false;

    const checkDate = new Date(2024, month - 1, day);
    return (
      checkDate.getFullYear() === 2024 &&
      checkDate.getMonth() === month - 1 &&
      checkDate.getDate() === day
    );
  };

  const initialValue = (showDateInput.value || '').trim();
  if (isValidMonthDay(initialValue)) {
    const [monthStr, dayStr] = initialValue.split('-');
    let year = new Date().getFullYear();
    if (monthStr === '02' && dayStr === '29') {
      while (!((year % 4 === 0 && year % 100 !== 0) || year % 400 === 0)) {
        year += 1;
      }
    }
    datePicker.value = `${year}-${initialValue}`;
  }

  datePicker.addEventListener('change', () => {
    showDateInput.value = datePicker.value ? datePicker.value.slice(5) : '';
  });

  clearDateBtn.addEventListener('click', () => {
    datePicker.value = '';
    showDateInput.value = '';
  });
});