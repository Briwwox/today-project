document.addEventListener('DOMContentLoaded', () => {
  document.querySelectorAll('.js-confirm-form').forEach((form) => {
    if (form.dataset.confirmBound === 'true') return;
    form.dataset.confirmBound = 'true';
    form.addEventListener('submit', (e) => {
      const msg = form.dataset.confirm || 'Вы уверены?';
      if (!confirm(msg)) {
        e.preventDefault();
      }
    });
  });

  document.querySelectorAll('#toastStack .toast-item').forEach((toast) => {
    if (toast.dataset.toastBound === 'true') return;
    toast.dataset.toastBound = 'true';

    const closeBtn = toast.querySelector('.toast-close');
    const hideToast = () => {
      toast.classList.add('is-hiding');
      setTimeout(() => toast.remove(), 300);
    };

    const timer = setTimeout(hideToast, 3500);

    closeBtn?.addEventListener('click', () => {
      clearTimeout(timer);
      hideToast();
    });
  });

  const fileInput = document.getElementById('avatarFileInput');
  const form = document.getElementById('avatarUploadForm');
  const panel = document.getElementById('cropperPanel');
  const saveBtn = document.getElementById('saveAvatarBtn');
  const stage = document.getElementById('cropperStage');
  const cropImg = document.getElementById('cropperImage');
  const zoomRange = document.getElementById('cropZoomRange');
  const resetBtn = document.getElementById('cropResetBtn');
  const miniCanvas = document.getElementById('miniPreviewCanvas');
  const miniCtx = miniCanvas ? miniCanvas.getContext('2d') : null;

  if (!fileInput || !form || !panel || !stage || !cropImg || !zoomRange || !miniCtx) return;

  const STAGE_SIZE = 240;
  const OUTPUT_SIZE = 400;

  let naturalW = 0;
  let naturalH = 0;
  let baseScale = 1;
  let zoom = 1;
  let offsetX = 0;
  let offsetY = 0;
  let isDragging = false;
  let startX = 0;
  let startY = 0;
  let objectUrl = null;
  let skipCropOnSubmit = false;
  let isProcessing = false;

  function clampOffsets() {
    const drawW = naturalW * baseScale * zoom;
    const drawH = naturalH * baseScale * zoom;
    const maxOffsetX = Math.max(0, (drawW - STAGE_SIZE) / 2);
    const maxOffsetY = Math.max(0, (drawH - STAGE_SIZE) / 2);
    offsetX = Math.min(maxOffsetX, Math.max(-maxOffsetX, offsetX));
    offsetY = Math.min(maxOffsetY, Math.max(-maxOffsetY, offsetY));
  }

  function renderPreview() {
    if (!naturalW || !naturalH) return;
    clampOffsets();

    const scale = baseScale * zoom;
    const drawW = naturalW * scale;
    const drawH = naturalH * scale;
    const left = (STAGE_SIZE - drawW) / 2 + offsetX;
    const top = (STAGE_SIZE - drawH) / 2 + offsetY;

    cropImg.style.width = `${drawW}px`;
    cropImg.style.height = `${drawH}px`;
    cropImg.style.left = `${left}px`;
    cropImg.style.top = `${top}px`;

    const ratio = miniCanvas.width / STAGE_SIZE;
    miniCtx.clearRect(0, 0, miniCanvas.width, miniCanvas.height);
    miniCtx.save();
    miniCtx.beginPath();
    miniCtx.arc(miniCanvas.width / 2, miniCanvas.height / 2, miniCanvas.width / 2, 0, Math.PI * 2);
    miniCtx.closePath();
    miniCtx.clip();
    miniCtx.drawImage(
      cropImg,
      left * ratio,
      top * ratio,
      drawW * ratio,
      drawH * ratio
    );
    miniCtx.restore();
  }

  function resetTransform() {
    if (!naturalW || !naturalH) return;
    baseScale = Math.max(STAGE_SIZE / naturalW, STAGE_SIZE / naturalH);
    zoom = 1;
    offsetX = 0;
    offsetY = 0;
    zoomRange.value = '1';
    renderPreview();
  }

  fileInput.addEventListener('change', () => {
    const file = fileInput.files && fileInput.files[0];
    if (!file) {
      panel.classList.add('hidden');
      saveBtn?.classList.add('hidden');
      naturalW = 0;
      naturalH = 0;
      return;
    }

    if (objectUrl) {
      URL.revokeObjectURL(objectUrl);
      objectUrl = null;
    }
    objectUrl = URL.createObjectURL(file);

    cropImg.onload = () => {
      naturalW = cropImg.naturalWidth;
      naturalH = cropImg.naturalHeight;
      if (!naturalW || !naturalH) return;
      panel.classList.remove('hidden');
      saveBtn?.classList.remove('hidden');
      resetTransform();
    };
    cropImg.src = objectUrl;
  });

  zoomRange.addEventListener('input', () => {
    zoom = parseFloat(zoomRange.value) || 1;
    renderPreview();
  });

  resetBtn?.addEventListener('click', resetTransform);

  stage.addEventListener('pointerdown', (e) => {
    if (!naturalW || !naturalH) return;
    isDragging = true;
    startX = e.clientX - offsetX;
    startY = e.clientY - offsetY;
    stage.setPointerCapture(e.pointerId);
  });

  stage.addEventListener('pointermove', (e) => {
    if (!isDragging) return;
    offsetX = e.clientX - startX;
    offsetY = e.clientY - startY;
    renderPreview();
  });

  const stopDrag = (e) => {
    if (!isDragging) return;
    isDragging = false;
    if (e && stage.hasPointerCapture(e.pointerId)) {
      stage.releasePointerCapture(e.pointerId);
    }
  };

  stage.addEventListener('pointerup', stopDrag);
  stage.addEventListener('pointercancel', stopDrag);

  form.addEventListener('submit', (e) => {
    if (skipCropOnSubmit || !naturalW || !naturalH) return;
    if (isProcessing) {
      e.preventDefault();
      return;
    }

    e.preventDefault();
    isProcessing = true;
    if (saveBtn) saveBtn.disabled = true;

    const scale = baseScale * zoom;
    const drawW = naturalW * scale;
    const drawH = naturalH * scale;
    const left = (STAGE_SIZE - drawW) / 2 + offsetX;
    const top = (STAGE_SIZE - drawH) / 2 + offsetY;

    const stageCanvas = document.createElement('canvas');
    stageCanvas.width = STAGE_SIZE;
    stageCanvas.height = STAGE_SIZE;
    const stageCtx = stageCanvas.getContext('2d');
    stageCtx.fillStyle = '#ffffff';
    stageCtx.fillRect(0, 0, STAGE_SIZE, STAGE_SIZE);
    stageCtx.drawImage(cropImg, left, top, drawW, drawH);

    const outCanvas = document.createElement('canvas');
    outCanvas.width = OUTPUT_SIZE;
    outCanvas.height = OUTPUT_SIZE;
    const outCtx = outCanvas.getContext('2d');
    outCtx.drawImage(stageCanvas, 0, 0, STAGE_SIZE, STAGE_SIZE, 0, 0, OUTPUT_SIZE, OUTPUT_SIZE);

    outCanvas.toBlob((blob) => {
      isProcessing = false;
      if (saveBtn) saveBtn.disabled = false;

      if (!blob) {
        skipCropOnSubmit = true;
        form.submit();
        return;
      }

      try {
        const croppedFile = new File([blob], 'avatar.jpg', { type: 'image/jpeg' });
        const dt = new DataTransfer();
        dt.items.add(croppedFile);
        fileInput.files = dt.files;
      } catch (_) {
      }

      skipCropOnSubmit = true;
      form.submit();
    }, 'image/jpeg', 0.9);
  });

  window.addEventListener('pagehide', () => {
    if (objectUrl) {
      URL.revokeObjectURL(objectUrl);
      objectUrl = null;
    }
  });
});