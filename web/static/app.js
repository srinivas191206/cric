let currentSection = 'stumps'; // 'stumps' | 'ball' | 'combined'
let currentTab = 'image';       // 'image' | 'video'
let currentFile = null;
let currentSampleId = null;

// Video Delivery Timeline Trim State
let trimState = {
  duration: 0,
  startTime: 0,
  endTime: 0,
  isPlayingPreview: false,
  objectUrl: null
};

document.addEventListener('DOMContentLoaded', () => {
  initSamples();
  initDragAndDrop();
  initSliders();
  initListeners();
  initTrimControls();
});

// Section Navigation Switcher
function switchSection(section) {
  currentSection = section;
  
  document.getElementById('nav-btn-stumps').classList.toggle('active', section === 'stumps');
  document.getElementById('nav-btn-ball').classList.toggle('active', section === 'ball');
  document.getElementById('nav-btn-combined').classList.toggle('active', section === 'combined');

  const stumpsSettings = document.getElementById('stumps-settings-card');
  const ballSettings = document.getElementById('ball-settings-card');
  const statMode = document.getElementById('stat-mode');
  const samplesTitle = document.getElementById('samples-title');

  if (section === 'stumps') {
    stumpsSettings.classList.remove('hidden');
    ballSettings.classList.add('hidden');
    statMode.innerText = "Stumps Vision";
    statMode.className = "tele-val text-green";
    samplesTitle.innerText = "Stump Test Scenarios";
  } else if (section === 'ball') {
    stumpsSettings.classList.add('hidden');
    ballSettings.classList.remove('hidden');
    statMode.innerText = "Ball Tracking";
    statMode.className = "tele-val text-ball";
    samplesTitle.innerText = "Ball Test Scenarios";
  } else {
    stumpsSettings.classList.remove('hidden');
    ballSettings.classList.remove('hidden');
    statMode.innerText = "Combined DRS";
    statMode.className = "tele-val text-accent";
    samplesTitle.innerText = "Match Test Scenarios";
  }

  // Reload relevant samples strip
  initSamples(section);

  // If media is already selected, re-run
  if (currentFile || currentSampleId) {
    runDetection();
  }
}

// Media Tab Switcher (Image vs Video)
function switchTab(tab) {
  currentTab = tab;
  document.getElementById('tab-image').classList.toggle('active', tab === 'image');
  document.getElementById('tab-video').classList.toggle('active', tab === 'video');

  const fileInput = document.getElementById('file-input');
  const uploadHeading = document.getElementById('upload-heading');
  const uploadFormats = document.getElementById('upload-formats');
  const trimCard = document.getElementById('video-trim-card');

  if (tab === 'image') {
    if (trimCard) trimCard.classList.add('hidden');
    fileInput.accept = "image/*";
    uploadHeading.innerText = currentSection === 'ball' ? "Drop cricket ball image here" : "Drop cricket image here";
    uploadFormats.innerText = "Supports JPG, PNG, WEBP, JPEG";
  } else {
    fileInput.accept = "video/*";
    uploadHeading.innerText = currentSection === 'ball' ? "Drop delivery video for ball tracking" : "Drop cricket video here";
    uploadFormats.innerText = "Supports MP4, MOV, AVI, WEBM, MKV";
    if (trimCard && currentFile && (currentFile.type.startsWith('video/') || ['.mp4', '.mov', '.avi', '.webm'].some(ext => currentFile.name.toLowerCase().endsWith(ext)))) {
      trimCard.classList.remove('hidden');
    }
  }

  // Reload samples appropriate for the active tab (image vs video)
  initSamples(currentSection);
}

// Sliders Initialization
function initSliders() {
  const confSlider = document.getElementById('conf-slider');
  const confValue = document.getElementById('conf-value');
  if (confSlider && confValue) {
    confSlider.addEventListener('input', (e) => {
      confValue.innerText = `${Math.round(e.target.value * 100)}%`;
    });
    confSlider.addEventListener('change', () => {
      if (currentFile || currentSampleId) runDetection();
    });
  }

  const ballConfSlider = document.getElementById('ball-conf-slider');
  const ballConfValue = document.getElementById('ball-conf-value');
  if (ballConfSlider && ballConfValue) {
    ballConfSlider.addEventListener('input', (e) => {
      ballConfValue.innerText = `${Math.round(e.target.value * 100)}%`;
    });
    ballConfSlider.addEventListener('change', () => {
      if (currentFile || currentSampleId) runDetection();
    });
  }

  const trailSlider = document.getElementById('trail-slider');
  const trailValue = document.getElementById('trail-value');
  if (trailSlider && trailValue) {
    trailSlider.addEventListener('input', (e) => {
      trailValue.innerText = `${e.target.value} f`;
    });
    trailSlider.addEventListener('change', () => {
      if (currentFile && currentTab === 'video') runDetection();
    });
  }
}

// Option Change Listeners
function initListeners() {
  const toggles = [
    'calib-toggle', 'render-mode-select', 'pitch-zones-toggle', 
    'batting-end-select', 'pitch-map-toggle'
  ];
  toggles.forEach(id => {
    const el = document.getElementById(id);
    if (el) {
      el.addEventListener('change', () => {
        if (currentFile || currentSampleId) runDetection();
      });
    }
  });
}

// Samples Strip
async function initSamples(catFilter = 'stumps') {
  const container = document.getElementById('samples-container');
  try {
    const mediaType = currentTab === 'video' ? 'video' : 'image';
    const res = await fetch(`/api/samples?category=${catFilter}&media_type=${mediaType}`);
    const samples = await res.json();
    container.innerHTML = '';

    samples.forEach(sample => {
      const card = document.createElement('div');
      card.className = 'sample-card' + (currentSampleId === sample.id ? ' active' : '');
      if (sample.media_type === 'video') {
        card.innerHTML = `
          <div style="background:#131b20; height:64px; display:flex; align-items:center; justify-content:center; border-radius:6px; border:1px solid #00eb7840;">
            <span style="font-size:1.4rem;">🎬</span>
          </div>
          <div class="sample-title">${sample.title}</div>
        `;
      } else {
        card.innerHTML = `
          <img src="${sample.url}" alt="${sample.title}">
          <div class="sample-title">${sample.title}</div>
        `;
      }
      card.onclick = () => selectSample(sample.id, sample.media_type);
      container.appendChild(card);
    });
  } catch (err) {
    console.error("Could not load samples:", err);
  }
}

function selectSample(sampleId, mediaType = 'image') {
  currentSampleId = sampleId;
  currentFile = null;
  if (mediaType === 'video' && currentTab !== 'video') {
    switchTab('video');
  } else if (mediaType === 'image' && currentTab !== 'image') {
    switchTab('image');
  }
  runDetection();
}

// Drag & Drop
function initDragAndDrop() {
  const dropZone = document.getElementById('drop-zone');
  const fileInput = document.getElementById('file-input');

  ['dragenter', 'dragover'].forEach(eventName => {
    dropZone.addEventListener(eventName, (e) => {
      e.preventDefault();
      e.stopPropagation();
      dropZone.classList.add('dragover');
    }, false);
  });

  ['dragleave', 'drop'].forEach(eventName => {
    dropZone.addEventListener(eventName, (e) => {
      e.preventDefault();
      e.stopPropagation();
      dropZone.classList.remove('dragover');
    }, false);
  });

  dropZone.addEventListener('drop', (e) => {
    const files = e.dataTransfer.files;
    if (files.length > 0) {
      handleFileSelected(files[0]);
    }
  });

  fileInput.addEventListener('change', (e) => {
    if (e.target.files.length > 0) {
      handleFileSelected(e.target.files[0]);
    }
  });
}

function triggerFileInput() {
  document.getElementById('file-input').click();
}

// --- VIDEO TIMELINE & DELIVERY TRIM CONTROLS ---

function formatSec(seconds) {
  if (isNaN(seconds) || seconds < 0) return "00:00.0";
  const mins = Math.floor(seconds / 60);
  const secs = seconds % 60;
  const minsStr = mins < 10 ? "0" + mins : mins;
  const secsStr = secs.toFixed(1).padStart(4, "0");
  return `${minsStr}:${secsStr}`;
}

function updateTimelineHighlight() {
  const highlight = document.getElementById('timeline-highlight');
  if (!highlight || trimState.duration <= 0) return;
  const leftPct = (trimState.startTime / trimState.duration) * 100;
  const widthPct = Math.max(0, ((trimState.endTime - trimState.startTime) / trimState.duration) * 100);
  highlight.style.left = `${leftPct}%`;
  highlight.style.width = `${widthPct}%`;
}

function updateTrimDurationBadge() {
  const badge = document.getElementById('trim-duration-badge');
  if (!badge) return;
  const diff = Math.max(0, trimState.endTime - trimState.startTime);
  badge.innerText = `Selected: ${diff.toFixed(1)}s (${trimState.startTime.toFixed(1)}s - ${trimState.endTime.toFixed(1)}s)`;
}

function initTrimControls() {
  const trimVideo = document.getElementById('trim-preview-video');
  const rangeStart = document.getElementById('trim-range-start');
  const rangeEnd = document.getElementById('trim-range-end');
  const numStart = document.getElementById('trim-start-num');
  const numEnd = document.getElementById('trim-end-num');
  const cursor = document.getElementById('timeline-cursor');
  const playheadBadge = document.getElementById('trim-playhead-time');
  const playBtn = document.getElementById('trim-play-btn');

  if (rangeStart) {
    rangeStart.addEventListener('input', (e) => {
      let val = parseFloat(e.target.value);
      if (val > trimState.endTime - 0.2) {
        val = Math.max(0, trimState.endTime - 0.2);
        e.target.value = val;
      }
      trimState.startTime = val;
      if (numStart) numStart.value = val.toFixed(1);
      if (trimVideo) trimVideo.currentTime = val;
      updateTimelineHighlight();
      updateTrimDurationBadge();
    });
  }

  if (rangeEnd) {
    rangeEnd.addEventListener('input', (e) => {
      let val = parseFloat(e.target.value);
      if (val < trimState.startTime + 0.2) {
        val = Math.min(trimState.duration, trimState.startTime + 0.2);
        e.target.value = val;
      }
      trimState.endTime = val;
      if (numEnd) numEnd.value = val.toFixed(1);
      if (trimVideo) trimVideo.currentTime = val;
      updateTimelineHighlight();
      updateTrimDurationBadge();
    });
  }

  if (trimVideo) {
    trimVideo.addEventListener('timeupdate', () => {
      if (playheadBadge) {
        playheadBadge.innerText = `${formatSec(trimVideo.currentTime)} / ${formatSec(trimState.duration)}`;
      }
      if (cursor && trimState.duration > 0) {
        const pct = (trimVideo.currentTime / trimState.duration) * 100;
        cursor.style.left = `${pct}%`;
      }
      if (trimState.isPlayingPreview && trimVideo.currentTime >= trimState.endTime) {
        trimVideo.pause();
        trimState.isPlayingPreview = false;
        if (playBtn) playBtn.innerText = "▶";
      }
    });

    trimVideo.addEventListener('pause', () => {
      if (playBtn) playBtn.innerText = "▶";
    });

    trimVideo.addEventListener('ended', () => {
      if (playBtn) playBtn.innerText = "▶";
      trimState.isPlayingPreview = false;
    });
  }
}

function initVideoTrim(file) {
  const trimCard = document.getElementById('video-trim-card');
  const trimVideo = document.getElementById('trim-preview-video');
  const rangeStart = document.getElementById('trim-range-start');
  const rangeEnd = document.getElementById('trim-range-end');
  const numStart = document.getElementById('trim-start-num');
  const numEnd = document.getElementById('trim-end-num');
  const playheadBadge = document.getElementById('trim-playhead-time');
  const playBtn = document.getElementById('trim-play-btn');

  if (!trimCard || !trimVideo) return;

  if (trimState.objectUrl) {
    URL.revokeObjectURL(trimState.objectUrl);
  }
  trimState.objectUrl = URL.createObjectURL(file);
  trimVideo.src = trimState.objectUrl;
  trimCard.classList.remove('hidden');

  trimVideo.onloadedmetadata = () => {
    trimState.duration = trimVideo.duration || 1.0;
    trimState.startTime = 0.0;
    trimState.endTime = trimState.duration;

    if (rangeStart) {
      rangeStart.min = "0";
      rangeStart.max = trimState.duration.toString();
      rangeStart.step = "0.05";
      rangeStart.value = "0";
    }

    if (rangeEnd) {
      rangeEnd.min = "0";
      rangeEnd.max = trimState.duration.toString();
      rangeEnd.step = "0.05";
      rangeEnd.value = trimState.duration.toString();
    }

    if (numStart) {
      numStart.min = "0";
      numStart.max = trimState.duration.toFixed(1);
      numStart.value = "0.0";
    }

    if (numEnd) {
      numEnd.min = "0";
      numEnd.max = trimState.duration.toFixed(1);
      numEnd.value = trimState.duration.toFixed(1);
    }

    if (playheadBadge) {
      playheadBadge.innerText = `00:00.0 / ${formatSec(trimState.duration)}`;
    }
    if (playBtn) playBtn.innerText = "▶";

    updateTimelineHighlight();
    updateTrimDurationBadge();
    trimVideo.currentTime = 0;
  };
}

function setTrimStartToCurrentTime() {
  const trimVideo = document.getElementById('trim-preview-video');
  if (!trimVideo || trimState.duration <= 0) return;
  const cur = parseFloat(trimVideo.currentTime.toFixed(1));
  const newStart = Math.max(0, Math.min(cur, trimState.endTime - 0.2));
  trimState.startTime = newStart;

  const rangeStart = document.getElementById('trim-range-start');
  const numStart = document.getElementById('trim-start-num');
  if (rangeStart) rangeStart.value = newStart;
  if (numStart) numStart.value = newStart.toFixed(1);

  updateTimelineHighlight();
  updateTrimDurationBadge();
}

function setTrimEndToCurrentTime() {
  const trimVideo = document.getElementById('trim-preview-video');
  if (!trimVideo || trimState.duration <= 0) return;
  const cur = parseFloat(trimVideo.currentTime.toFixed(1));
  const newEnd = Math.min(trimState.duration, Math.max(cur, trimState.startTime + 0.2));
  trimState.endTime = newEnd;

  const rangeEnd = document.getElementById('trim-range-end');
  const numEnd = document.getElementById('trim-end-num');
  if (rangeEnd) rangeEnd.value = newEnd;
  if (numEnd) numEnd.value = newEnd.toFixed(1);

  updateTimelineHighlight();
  updateTrimDurationBadge();
}

function syncTrimFromNumberInputs() {
  const numStart = document.getElementById('trim-start-num');
  const numEnd = document.getElementById('trim-end-num');
  const rangeStart = document.getElementById('trim-range-start');
  const rangeEnd = document.getElementById('trim-range-end');
  const trimVideo = document.getElementById('trim-preview-video');

  let s = parseFloat(numStart.value) || 0;
  let e = parseFloat(numEnd.value) || trimState.duration;

  if (s < 0) s = 0;
  if (e > trimState.duration && trimState.duration > 0) e = trimState.duration;
  if (s > e - 0.2) s = Math.max(0, e - 0.2);

  trimState.startTime = s;
  trimState.endTime = e;

  numStart.value = s.toFixed(1);
  numEnd.value = e.toFixed(1);
  if (rangeStart) rangeStart.value = s;
  if (rangeEnd) rangeEnd.value = e;

  if (trimVideo) trimVideo.currentTime = s;
  updateTimelineHighlight();
  updateTrimDurationBadge();
}

function toggleTrimVideoPlay() {
  const trimVideo = document.getElementById('trim-preview-video');
  const playBtn = document.getElementById('trim-play-btn');
  if (!trimVideo) return;

  if (trimVideo.paused) {
    trimState.isPlayingPreview = false;
    trimVideo.play();
    if (playBtn) playBtn.innerText = "❚❚";
  } else {
    trimVideo.pause();
    if (playBtn) playBtn.innerText = "▶";
  }
}

function playTrimPreview() {
  const trimVideo = document.getElementById('trim-preview-video');
  const playBtn = document.getElementById('trim-play-btn');
  if (!trimVideo || trimState.duration <= 0) return;

  trimVideo.currentTime = trimState.startTime;
  trimState.isPlayingPreview = true;
  trimVideo.play();
  if (playBtn) playBtn.innerText = "❚❚";
}

function handleFileSelected(file) {
  currentFile = file;
  currentSampleId = null;

  const isVideo = file.type.startsWith('video/') || 
    ['.mp4', '.mov', '.avi', '.webm'].some(ext => file.name.toLowerCase().endsWith(ext));

  if (isVideo) {
    if (currentTab !== 'video') {
      switchTab('video');
    }
    initVideoTrim(file);
    const trimCard = document.getElementById('video-trim-card');
    if (trimCard) {
      trimCard.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
    }
  } else {
    const trimCard = document.getElementById('video-trim-card');
    if (trimCard) trimCard.classList.add('hidden');
    if (currentTab !== 'image') {
      switchTab('image');
    }
    runDetection();
  }
}

// Execute Inference
async function runDetection() {
  const loading = document.getElementById('loading-overlay');
  const loadingText = document.getElementById('loading-text');
  loading.classList.remove('hidden');

  const conf = parseFloat(document.getElementById('conf-slider').value);
  const ballConf = parseFloat(document.getElementById('ball-conf-slider').value);
  const trailLen = parseInt(document.getElementById('trail-slider').value);
  const calibToggle = document.getElementById('calib-toggle');
  const pitchCalibration = calibToggle ? calibToggle.checked : true;
  const renderMode = document.getElementById('render-mode-select').value;
  const showPitchZones = document.getElementById('pitch-zones-toggle').checked;
  const battingEnd = document.getElementById('batting-end-select').value;

  // IMAGE PIPELINE
  if (currentTab === 'image') {
    loadingText.innerText = currentSection === 'ball' ? "Detecting cricket ball..." : "Analyzing cricket wickets & pitch...";
    const formData = new FormData();
    if (currentFile) {
      formData.append('file', currentFile);
    } else if (currentSampleId) {
      formData.append('sample_id', currentSampleId);
    } else {
      loading.classList.add('hidden');
      return;
    }

    let url = '/api/detect';
    if (currentSection === 'ball') {
      url = '/api/detect-ball';
      formData.append('ball_conf', ballConf);
      formData.append('detect_stumps', false);
      formData.append('pitch_calibration', false);
    } else if (currentSection === 'combined') {
      url = '/api/detect-ball';
      formData.append('ball_conf', ballConf);
      formData.append('detect_stumps', true);
      formData.append('pitch_calibration', pitchCalibration);
      formData.append('render_mode', renderMode);
      formData.append('show_pitch_zones', showPitchZones);
      formData.append('batting_end', battingEnd);
    } else {
      formData.append('conf', conf);
      formData.append('pitch_calibration', pitchCalibration);
      formData.append('render_mode', renderMode);
      formData.append('show_pitch_zones', showPitchZones);
      formData.append('batting_end', battingEnd);
    }

    try {
      const res = await fetch(url, { method: 'POST', body: formData });
      const data = await res.json();
      if (data.success) {
        if (currentSection === 'stumps') {
          renderImageResult(data);
        } else {
          renderBallImageResult(data);
        }
      } else {
        alert(data.detail || "Detection failed");
      }
    } catch (err) {
      console.error(err);
      alert("Error processing image");
    } finally {
      loading.classList.add('hidden');
    }
  } 
  // VIDEO PIPELINE
  else {
    if (!currentFile && !currentSampleId) {
      alert("Please upload a video file or click a sample delivery clip.");
      loading.classList.add('hidden');
      return;
    }

    const formData = new FormData();
    if (currentFile) {
      formData.append('file', currentFile);
    } else if (currentSampleId) {
      formData.append('sample_id', currentSampleId);
    }

    if (trimState.duration > 0 && trimState.endTime > trimState.startTime) {
      formData.append('start_time', trimState.startTime);
      formData.append('end_time', trimState.endTime);
      loadingText.innerText = currentSection === 'stumps' 
        ? `Locking pitch calibration (${trimState.startTime.toFixed(1)}s - ${trimState.endTime.toFixed(1)}s)...` 
        : `Tracking delivery trajectory (${trimState.startTime.toFixed(1)}s - ${trimState.endTime.toFixed(1)}s)...`;
    } else {
      loadingText.innerText = currentSection === 'stumps' 
        ? "Locking pitch calibration and processing video..." 
        : "Tracking ball trajectory along pitch corridor...";
    }

    let url = '/api/detect-video';
    if (currentSection === 'stumps') {
      formData.append('conf', conf);
      formData.append('pitch_calibration', pitchCalibration);
      formData.append('render_mode', renderMode);
      formData.append('show_pitch_zones', showPitchZones);
      formData.append('batting_end', battingEnd);
    } else {
      url = '/api/track-ball-video';
      formData.append('ball_conf', ballConf);
      formData.append('trail_length', trailLen);
      formData.append('detect_stumps', currentSection === 'combined');
      formData.append('pitch_calibration', pitchCalibration);
      formData.append('render_mode', renderMode);
      formData.append('show_pitch_zones', showPitchZones);
      formData.append('batting_end', battingEnd);
    }

    try {
      const res = await fetch(url, { method: 'POST', body: formData });
      if (!res.ok) {
        const errJson = await res.json().catch(() => null);
        throw new Error(errJson && errJson.detail ? errJson.detail : `Server returned status ${res.status}`);
      }
      const data = await res.json();
      if (data.success) {
        if (currentSection === 'stumps') {
          renderVideoResult(data);
        } else {
          renderBallVideoResult(data);
        }
      } else {
        alert(data.detail || "Video processing failed");
      }
    } catch (err) {
      console.error("Video processing error:", err);
      alert("Error processing video: " + (err.message || err));
    } finally {
      loading.classList.add('hidden');
    }
  }
}

// Render Results: Stumps Image
function renderImageResult(data) {
  document.getElementById('empty-state').classList.add('hidden');
  document.getElementById('video-display-wrapper').classList.add('hidden');
  document.getElementById('ball-tracking-card').classList.add('hidden');
  
  const imgWrapper = document.getElementById('image-display-wrapper');
  const resultImg = document.getElementById('result-image');
  resultImg.src = data.image_data;
  imgWrapper.classList.remove('hidden');

  // Telemetry
  document.getElementById('tele-label-1').innerText = "Wickets";
  document.getElementById('stat-count').innerText = `${data.num_wickets} Wicket${data.num_wickets === 1 ? '' : 's'}`;
  document.getElementById('stat-latency').innerText = `${data.inference_ms} ms (${data.fps_estimate} FPS)`;
  document.getElementById('tele-label-3').innerText = "Resolution";
  document.getElementById('stat-res').innerText = `${data.image_size.width} × ${data.image_size.height}`;

  // Calibration Telemetry
  const calibCard = document.getElementById('calibration-card');
  if (data.calibration && data.calibration.active) {
    calibCard.classList.remove('hidden');
    document.getElementById('calib-status-badge').className = 'badge-calib-active';
    document.getElementById('calib-status-badge').innerText = 'CALIBRATED (2 WICKETS)';
    document.getElementById('calib-dist-px').innerText = `${data.calibration.distance_px} px`;
    document.getElementById('calib-scale').innerText = `${data.calibration.px_per_meter} px/m`;
    document.getElementById('calib-near-pt').innerText = `(${data.calibration.near_ground_ref[0]}, ${data.calibration.near_ground_ref[1]})`;
    document.getElementById('calib-far-pt').innerText = `(${data.calibration.far_ground_ref[0]}, ${data.calibration.far_ground_ref[1]})`;
  } else {
    calibCard.classList.add('hidden');
  }

  // Download
  const dlBtn = document.getElementById('download-btn');
  dlBtn.href = data.download_url;
  dlBtn.download = `detected_${data.filename}`;

  // Box Breakdown
  const detCard = document.getElementById('detections-card');
  const boxesList = document.getElementById('boxes-list');
  detCard.classList.remove('hidden');
  boxesList.innerHTML = '';

  if (data.boxes.length === 0) {
    boxesList.innerHTML = `<p style="color: var(--text-muted); font-size: 0.88rem;">No stumps detected above threshold.</p>`;
  } else {
    data.boxes.forEach((b, idx) => {
      const item = document.createElement('div');
      item.className = 'box-item';
      item.innerHTML = `
        <div>
          <div class="box-title">Wicket #${idx + 1}</div>
          <div class="box-coords">Coords: [${b.box.join(', ')}] · Size: ${b.width}×${b.height}px</div>
        </div>
        <div class="box-conf-pill">${Math.round(b.confidence * 100)}% Conf</div>
      `;
      boxesList.appendChild(item);
    });
  }
}

// Render Results: Ball Image
function renderBallImageResult(data) {
  document.getElementById('empty-state').classList.add('hidden');
  document.getElementById('video-display-wrapper').classList.add('hidden');
  
  const imgWrapper = document.getElementById('image-display-wrapper');
  const resultImg = document.getElementById('result-image');
  resultImg.src = data.image_data;
  imgWrapper.classList.remove('hidden');

  // Telemetry
  document.getElementById('tele-label-1').innerText = "Ball Status";
  document.getElementById('stat-count').innerText = data.ball_detected ? "DETECTED" : "NOT DETECTED";
  document.getElementById('stat-count').className = data.ball_detected ? "tele-val text-ball" : "tele-val text-muted";
  document.getElementById('stat-latency').innerText = `${data.inference_ms} ms (${data.fps_estimate} FPS)`;
  document.getElementById('tele-label-3').innerText = "Resolution";
  document.getElementById('stat-res').innerText = `${data.image_size.width} × ${data.image_size.height}`;

  // Ball Card
  const ballCard = document.getElementById('ball-tracking-card');
  ballCard.classList.remove('hidden');
  if (data.ball_detected) {
    const ball = data.ball_detections[0];
    document.getElementById('ball-status-badge').className = 'badge-ball-active';
    document.getElementById('ball-status-badge').innerText = 'BALL DETECTED';
    document.getElementById('ball-confidence-val').innerText = `${Math.round(ball.confidence * 100)}%`;
    document.getElementById('ball-trail-pts').innerText = `1 Point (${Math.round(ball.center[0])}, ${Math.round(ball.center[1])})`;

    const flightEl = document.getElementById('ball-flight-status');
    const flightSub = document.getElementById('ball-flight-sub');
    if (data.pitch_mapping) {
      if (flightEl) flightEl.innerText = `${data.pitch_mapping.dist_from_crease_m} m`;
      if (flightSub) flightSub.innerText = `Zone: ${data.pitch_mapping.zone.toUpperCase()}`;
      document.getElementById('ball-pitch-line').innerText = data.pitch_mapping.line;
    } else {
      if (flightEl) flightEl.innerText = `Tracked`;
      if (flightSub) flightSub.innerText = `Pitch calibration needed`;
      document.getElementById('ball-pitch-line').innerText = `—`;
    }
  } else {
    document.getElementById('ball-status-badge').className = 'badge-calib-inactive';
    document.getElementById('ball-status-badge').innerText = 'NO BALL IN FRAME';
    const flightEl = document.getElementById('ball-flight-status');
    const flightSub = document.getElementById('ball-flight-sub');
    if (flightEl) flightEl.innerText = `—`;
    if (flightSub) flightSub.innerText = `—`;
    document.getElementById('ball-pitch-line').innerText = `—`;
    document.getElementById('ball-trail-pts').innerText = `0 Points`;
    document.getElementById('ball-confidence-val').innerText = `—`;
  }

  // Calibration card if combined
  const calibCard = document.getElementById('calibration-card');
  if (data.calibration && data.calibration.active) {
    calibCard.classList.remove('hidden');
    document.getElementById('calib-dist-px').innerText = `${data.calibration.distance_px} px`;
    document.getElementById('calib-scale').innerText = `${data.calibration.px_per_meter} px/m`;
    document.getElementById('calib-near-pt').innerText = `(${data.calibration.near_ground_ref[0]}, ${data.calibration.near_ground_ref[1]})`;
    document.getElementById('calib-far-pt').innerText = `(${data.calibration.far_ground_ref[0]}, ${data.calibration.far_ground_ref[1]})`;
  } else {
    calibCard.classList.add('hidden');
  }

  // Download
  const dlBtn = document.getElementById('download-btn');
  dlBtn.href = data.download_url;
  dlBtn.download = `detected_ball_${data.filename}`;

  // Breakdown Card
  const detCard = document.getElementById('detections-card');
  const boxesList = document.getElementById('boxes-list');
  detCard.classList.remove('hidden');
  boxesList.innerHTML = '';

  if (data.ball_detections.length === 0) {
    boxesList.innerHTML = `<p style="color: var(--text-muted); font-size: 0.88rem;">No ball detected. Try lowering the ball confidence slider.</p>`;
  } else {
    data.ball_detections.forEach((b, idx) => {
      const item = document.createElement('div');
      item.className = 'box-item';
      item.innerHTML = `
        <div>
          <div class="box-title" style="color: #ff9f1c;">Cricket Ball #${idx + 1}</div>
          <div class="box-coords">Center: (${Math.round(b.center[0])}, ${Math.round(b.center[1])}) · Radius: ${b.radius}px</div>
        </div>
        <div class="box-conf-pill" style="border-color: #ff9f1c; color: #ff9f1c;">${Math.round(b.confidence * 100)}% Conf</div>
      `;
      boxesList.appendChild(item);
    });
  }
}

// Render Results: Stumps Video
function renderVideoResult(data) {
  document.getElementById('empty-state').classList.add('hidden');
  document.getElementById('image-display-wrapper').classList.add('hidden');
  document.getElementById('ball-tracking-card').classList.add('hidden');

  const videoWrapper = document.getElementById('video-display-wrapper');
  const resultVideo = document.getElementById('result-video');
  resultVideo.src = data.video_url;
  resultVideo.muted = true;
  videoWrapper.classList.remove('hidden');
  resultVideo.play().catch(e => console.log('Autoplay deferred:', e));

  // Telemetry
  document.getElementById('tele-label-1').innerText = "Total Detections";
  document.getElementById('stat-count').innerText = `${data.total_stump_detections || 0} Wickets`;
  document.getElementById('stat-latency').innerText = `${data.avg_fps || 0} FPS`;
  document.getElementById('tele-label-3').innerText = "Frames";
  document.getElementById('stat-res').innerText = `${data.frames_processed || 0} Frames`;

  // Download
  const dlBtn = document.getElementById('download-btn');
  dlBtn.href = data.video_url;
  dlBtn.download = `detected_${data.filename || 'video.mp4'}`;

  const detCard = document.getElementById('detections-card');
  const boxesList = document.getElementById('boxes-list');
  detCard.classList.remove('hidden');
  boxesList.innerHTML = `
    <div class="box-item" style="grid-column: 1 / -1;">
      <div>
        <div class="box-title">Constant Stumps Video Processed</div>
        <div class="box-coords">Duration: ${data.duration_sec || 0}s · Processed in ${data.processing_time_sec || 0}s · Speed: ${data.avg_fps || 0} FPS · Calibration: Locked</div>
      </div>
      <div class="box-conf-pill">Completed</div>
    </div>
  `;
}

// Render Results: Ball Video Tracking
function renderBallVideoResult(data) {
  document.getElementById('empty-state').classList.add('hidden');
  document.getElementById('image-display-wrapper').classList.add('hidden');

  const videoWrapper = document.getElementById('video-display-wrapper');
  const resultVideo = document.getElementById('result-video');
  resultVideo.src = data.video_url;
  resultVideo.muted = true;
  videoWrapper.classList.remove('hidden');
  resultVideo.play().catch(e => console.log('Autoplay deferred:', e));

  // Telemetry
  document.getElementById('tele-label-1').innerText = "Ball Flight";
  document.getElementById('stat-count').innerText = `${data.ball_frames_tracked || 0} Frames`;
  document.getElementById('stat-count').className = "tele-val text-ball";
  document.getElementById('stat-latency').innerText = `${data.avg_fps || 0} FPS`;
  document.getElementById('tele-label-3').innerText = "Total Video";
  document.getElementById('stat-res').innerText = `${data.frames_processed || 0} Frames`;

  // Ball Telemetry Card
  const ballCard = document.getElementById('ball-tracking-card');
  ballCard.classList.remove('hidden');
  document.getElementById('ball-status-badge').innerText = 'TRAJECTORY TRACKED';
  document.getElementById('ball-trail-pts').innerText = `${data.ball_frames_tracked || 0} frames in flight`;
  document.getElementById('ball-confidence-val').innerText = 'Active Track';

  const flightEl = document.getElementById('ball-flight-status');
  const flightSub = document.getElementById('ball-flight-sub');
  if (flightEl) flightEl.innerText = `${data.ball_frames_tracked || 0} Frames`;
  if (flightSub) flightSub.innerText = data.ball_frames_tracked > 0 ? "Trajectory Tracked" : "No Ball";
  document.getElementById('ball-pitch-line').innerText = data.ball_frames_tracked > 0 ? "Corridor Aligned" : "—";

  // Download
  const dlBtn = document.getElementById('download-btn');
  dlBtn.href = data.video_url;
  dlBtn.download = `ball_tracked_${data.filename}`;

  // Card summary
  const detCard = document.getElementById('detections-card');
  const boxesList = document.getElementById('boxes-list');
  detCard.classList.remove('hidden');
  const bounceTxt = data.bounce_detected && data.bounce_event 
    ? ` · Pitch Impact: ${data.bounce_event.dist_from_crease_m}m (${data.bounce_event.zone}) · Line: ${data.bounce_event.lateral_line}` 
    : '';

  boxesList.innerHTML = `
    <div class="box-item" style="grid-column: 1 / -1;">
      <div>
        <div class="box-title" style="color: #00eb78;">IPL Hawk-Eye DRS 3D Trajectory Active</div>
        <div class="box-coords">Tracked ${data.ball_frames_tracked} frames across ${data.frames_processed} total frames · Kalman Filter: Locked · Processed in ${data.processing_time_sec}s (${data.avg_fps} FPS)${bounceTxt}</div>
      </div>
      <div class="box-conf-pill" style="border-color: #00eb78; color: #00eb78;">Hawk-Eye Ready</div>
    </div>
  `;
}
