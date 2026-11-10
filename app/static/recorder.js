/**
 * Sahayak Client Architecture (Phase 3 Redesign)
 * Single AudioPlayer module + 5-State Call Machine + Barge-In VAD
 */

// -------------------------------------------------------------
// 1. UNIFIED AUDIO PLAYER MODULE (B1)
// -------------------------------------------------------------
class AudioPlayer {
  constructor() {
    this.currentAudio = null;
    this.queue = [];
    this.isPlaying = false;
    this.onEndedCallback = null;
    this.activeGeneration = 0;
  }

  play(base64Audio, onEnded = null, generation = 0) {
    this.stop(); // Stop any active playback immediately within 200ms
    this.activeGeneration = generation;
    this.onEndedCallback = onEnded;
    this.isPlaying = true;

    try {
      this.currentAudio = new Audio("data:audio/wav;base64," + base64Audio);
      
      this.currentAudio.onended = () => {
        if (this.activeGeneration !== generation) return; // Stale check
        this.isPlaying = false;
        this.currentAudio = null;
        if (this.onEndedCallback) {
          const cb = this.onEndedCallback;
          this.onEndedCallback = null;
          cb();
        }
      };

      this.currentAudio.onerror = (e) => {
        console.error("AudioPlayer error:", e);
        this.isPlaying = false;
        this.currentAudio = null;
      };

      const playPromise = this.currentAudio.play();
      if (playPromise !== undefined) {
        playPromise.catch(err => {
          console.warn("Audio autoplay rejected:", err);
          this.isPlaying = false;
        });
      }
    } catch (e) {
      console.error("Failed to play audio:", e);
      this.isPlaying = false;
    }
  }

  stop() {
    this.activeGeneration++;
    if (this.currentAudio) {
      this.currentAudio.pause();
      this.currentAudio.src = "";
      this.currentAudio.load();
      this.currentAudio = null;
    }
    this.queue = [];
    this.isPlaying = false;
    this.onEndedCallback = null;
  }
}

// -------------------------------------------------------------
// 2. UNIFIED CALL STATE MACHINE (B1, B3)
// States: IDLE, LISTENING, THINKING, SPEAKING, ENDED
// -------------------------------------------------------------
const player = new AudioPlayer();

let callState = "IDLE";
let callGeneration = 0;
let currentTurnId = 0;
let inFlightAbortController = null;

let sessionId = null;
let currentLanguage = "hi-IN";
let audioContext = null;
let mediaStream = null;
let scriptProcessor = null;
let pcmSamples = [];
let preRollBuffer = []; // 300ms pre-roll buffer for barge-in

let isCallMode = false;
let callTimerInterval = null;
let callSeconds = 0;
let silenceTimer = null;
let speakingStartTime = 0;
let lastAgentAudioBase64 = null;

// DOM Elements
const recordBtn = document.getElementById("recordBtn");
const recordIcon = document.getElementById("recordIcon");
const recordStatus = document.getElementById("recordStatus");
const recordSubStatus = document.getElementById("recordSubStatus");
const callStateBadge = document.getElementById("callStateBadge");
const chatBox = document.getElementById("chatBox");
const startCallBtn = document.getElementById("startCallBtn");
const endCallBtn = document.getElementById("endCallBtn");
const replayBtn = document.getElementById("replayBtn");
const demoModeBtn = document.getElementById("demoModeBtn");
const callTimerBadge = document.getElementById("callTimerBadge");
const callTimer = document.getElementById("callTimer");
const audioMeterBar = document.getElementById("audioMeterBar");
const dbValue = document.getElementById("dbValue");
const audioWarning = document.getElementById("audioWarning");
const audioWarningText = document.getElementById("audioWarningText");
const textSizeBtn = document.getElementById("textSizeBtn");
const langChips = document.querySelectorAll(".lang-chip");
const activeSchemePill = document.getElementById("activeSchemePill");
const summaryScheme = document.getElementById("summaryScheme");
const summaryPrimary = document.getElementById("summaryPrimary");
const summarySecondary = document.getElementById("summarySecondary");
const summaryExclusion = document.getElementById("summaryExclusion");
const suggestionChips = document.getElementById("suggestionChips");
const trySayingLabel = document.getElementById("trySayingLabel");
const latencyDetails = document.getElementById("latencyDetails");
const latVal = document.getElementById("latVal");

// Scheme Cards
const schemeCards = {
  pm_kisan: document.getElementById("card_pm_kisan"),
  ration_card: document.getElementById("card_ration_card"),
  nsap_pension: document.getElementById("card_nsap_pension")
};

// Suggestions by Language
const SUGGESTIONS = {
  "hi-IN": [
    "पीएम किसान योजना",
    "नया राशन कार्ड",
    "वृद्धावस्था पेंशन",
    "हाँ ज़मीन है",
    "उम्र 65 साल"
  ],
  "en-IN": [
    "PM Kisan eligibility",
    "Apply for Ration card",
    "Old age pension",
    "I own 2 acres of land",
    "My age is 68"
  ],
  "ta-IN": [
    "பிஎம் கிசான் திட்டம்",
    "ரேஷன் கார்டு",
    "முதியோர் ஓய்வூதியம்",
    "ஆம் நிலம் உள்ளது",
    "வயது 62"
  ]
};

// Set State with explicit UI transitions
function setCallState(newState) {
  callState = newState;
  
  // Update state badge
  let badgeColor = "bg-slate-100 text-slate-700 border-slate-200";
  let dotColor = "bg-slate-400";
  
  if (newState === "LISTENING") {
    badgeColor = "bg-rose-100 text-rose-800 border-rose-300";
    dotColor = "bg-rose-500 animate-pulse";
  } else if (newState === "THINKING") {
    badgeColor = "bg-amber-100 text-amber-800 border-amber-300";
    dotColor = "bg-amber-500 animate-spin";
  } else if (newState === "SPEAKING") {
    badgeColor = "bg-blue-100 text-blue-800 border-blue-300";
    dotColor = "bg-blue-500 animate-bounce";
  } else if (newState === "ENDED") {
    badgeColor = "bg-slate-200 text-slate-600 border-slate-300";
    dotColor = "bg-slate-400";
  }

  callStateBadge.className = `px-3 py-1 rounded-full text-xs font-bold tracking-wide uppercase border flex items-center gap-1.5 ${badgeColor}`;
  callStateBadge.innerHTML = `<span class="w-2 h-2 rounded-full ${dotColor}"></span> ${newState}`;

  // Update Orb Visuals
  recordBtn.className = "w-24 h-24 rounded-full text-white flex items-center justify-center shadow-lg transition-all duration-300 focus:outline-none cursor-pointer";
  if (newState === "LISTENING") {
    recordBtn.classList.add("orb-listening");
    recordIcon.className = "fa-solid fa-microphone text-3xl";
    recordStatus.textContent = isCallMode ? "Listening hands-free..." : "Listening... Click to stop";
    recordSubStatus.textContent = "Speak clearly into your microphone";
  } else if (newState === "THINKING") {
    recordBtn.classList.add("orb-thinking");
    recordIcon.className = "fa-solid fa-spinner fa-spin text-3xl";
    recordStatus.textContent = "Evaluating deterministic rules...";
    recordSubStatus.textContent = "Running sovereign eligibility logic without LLM";
  } else if (newState === "SPEAKING") {
    recordBtn.classList.add("orb-speaking");
    recordIcon.className = "fa-solid fa-volume-high text-3xl";
    recordStatus.textContent = "Agent speaking (Interrupt anytime)...";
    recordSubStatus.textContent = "Barge-in active: simply speak to interrupt the agent";
  } else if (newState === "ENDED") {
    recordBtn.classList.add("orb-idle");
    recordIcon.className = "fa-solid fa-phone-slash text-3xl";
    recordStatus.textContent = "Call Ended";
    recordSubStatus.textContent = "Click Start Call or microphone to begin a new assessment";
  } else {
    recordBtn.classList.add("orb-idle");
    recordIcon.className = "fa-solid fa-microphone text-3xl";
    recordStatus.textContent = "Tap to Speak or Start Call";
    recordSubStatus.textContent = "Continuous hands-free conversation with interrupt capability";
  }
}

// Language Selector Handler
langChips.forEach(chip => {
  chip.addEventListener("click", () => {
    langChips.forEach(c => {
      c.className = "lang-chip min-h-[44px] px-3.5 py-1.5 rounded-lg text-xs font-bold transition text-emerald-200 hover:text-white";
    });
    chip.className = "lang-chip min-h-[44px] px-3.5 py-1.5 rounded-lg text-xs font-bold transition bg-emerald-600 text-white shadow-sm";
    currentLanguage = chip.dataset.lang;
    initSession();
  });
});

// Text Size Toggle
let isLargeText = false;
textSizeBtn.addEventListener("click", () => {
  isLargeText = !isLargeText;
  document.body.classList.toggle("text-lg-mode", isLargeText);
});

// Update Suggestion Chips
function renderSuggestions() {
  suggestionChips.innerHTML = "";
  const list = SUGGESTIONS[currentLanguage] || SUGGESTIONS["en-IN"];
  list.forEach(phrase => {
    const btn = document.createElement("button");
    btn.className = "px-2.5 py-1 bg-slate-100 hover:bg-emerald-50 hover:text-emerald-800 hover:border-emerald-300 border border-slate-200 rounded-lg text-[11px] font-medium text-slate-700 transition cursor-pointer";
    btn.textContent = phrase;
    btn.onclick = () => simulateTurn(phrase);
    suggestionChips.appendChild(btn);
  });
}

// Initialize Session on Load
async function initSession() {
  chatBox.innerHTML = "";
  renderSuggestions();
  player.stop();
  resetCaseSummary();
  hideWarning();
  
  try {
    const formData = new FormData();
    formData.append("language", currentLanguage);
    const res = await fetch("/api/session/start", { method: "POST", body: formData });
    const data = await res.json();
    sessionId = data.session_id;
    appendAgentBubble(data.agent_text);
    if (data.audio_base64) {
      lastAgentAudioBase64 = data.audio_base64;
      if (isCallMode) {
        startAgentSpeaking(data.audio_base64);
      }
    }
  } catch (err) {
    console.error("Failed to start session:", err);
  }
}

window.addEventListener("DOMContentLoaded", () => {
  initSession();
});

// UI Bubble Appenders
function appendUserBubble(text) {
  const wrapper = document.createElement("div");
  wrapper.className = "flex items-start justify-end gap-2.5";
  wrapper.innerHTML = `
    <div class="bg-emerald-700 text-white rounded-2xl rounded-tr-none p-3.5 text-xs sm:text-sm shadow-sm max-w-[85%] leading-relaxed">
      <p>${text}</p>
    </div>
    <div class="w-8 h-8 rounded-full bg-slate-200 text-slate-700 flex items-center justify-center flex-shrink-0 text-xs font-bold shadow-xs">
      <i class="fa-solid fa-user"></i>
    </div>
  `;
  chatBox.appendChild(wrapper);
  chatBox.scrollTop = chatBox.scrollHeight;
}

function appendAgentBubble(text, evalData = null) {
  const wrapper = document.createElement("div");
  wrapper.className = "flex items-start gap-2.5";
  
  let resultCardHtml = "";
  if (evalData && evalData.verdict) {
    const isEligible = evalData.verdict === "LIKELY_ELIGIBLE";
    const badgeColor = isEligible ? "bg-emerald-100 text-emerald-800 border-emerald-300" : "bg-rose-100 text-rose-800 border-rose-300";
    const icon = isEligible ? "fa-circle-check" : "fa-circle-xmark";
    
    let docsHtml = "";
    if (evalData.documents && evalData.documents.length > 0) {
      docsHtml = `
        <div class="mt-2.5 pt-2 border-t border-slate-200">
          <p class="font-bold text-[11px] text-slate-700 mb-1">Required Documents / आवश्यक दस्तावेज़:</p>
          <ul class="list-disc list-inside text-[11px] text-slate-600 space-y-0.5">
            ${evalData.documents.map(d => `<li>${d}</li>`).join("")}
          </ul>
        </div>
      `;
    }

    resultCardHtml = `
      <div class="mt-3 p-3 bg-white border border-slate-200 rounded-xl shadow-xs">
        <div class="flex items-center gap-2 mb-1.5">
          <span class="px-2.5 py-0.5 rounded text-[11px] font-bold border ${badgeColor} flex items-center gap-1">
            <i class="fa-solid ${icon}"></i> ${evalData.verdict}
          </span>
          <span class="text-[10px] text-slate-400 uppercase font-semibold">${evalData.scheme_id}</span>
        </div>
        ${docsHtml}
        <p class="mt-2 text-[10px] text-slate-400 italic">Note: Indicative assessment. Confirm with official department.</p>
      </div>
    `;
  }

  wrapper.innerHTML = `
    <div class="w-8 h-8 rounded-full bg-emerald-800 text-amber-300 flex items-center justify-center flex-shrink-0 text-xs font-bold shadow-xs">
      स
    </div>
    <div class="bg-slate-100 text-slate-800 rounded-2xl rounded-tl-none p-3.5 text-xs sm:text-sm shadow-sm max-w-[85%] leading-relaxed border border-slate-200/50">
      <p>${text}</p>
      ${resultCardHtml}
    </div>
  `;
  chatBox.appendChild(wrapper);
  chatBox.scrollTop = chatBox.scrollHeight;
}

// Case Summary Updates
function updateCaseSummary(schemeId, slots, evalRes) {
  if (schemeId) {
    activeSchemePill.textContent = schemeId.toUpperCase().replace("_", " ");
    activeSchemePill.className = "px-2.5 py-0.5 rounded-full text-[10px] font-bold bg-amber-100 text-amber-900 border border-amber-300";
    summaryScheme.textContent = schemeId.replace("_", " ").toUpperCase();

    // Highlight Scheme Card
    Object.keys(schemeCards).forEach(k => {
      if (schemeCards[k]) {
        if (k === schemeId) {
          schemeCards[k].className = "scheme-card p-3 rounded-xl border-2 border-emerald-500 bg-emerald-50/50 shadow-sm transition flex items-center gap-3";
        } else {
          schemeCards[k].className = "scheme-card p-3 rounded-xl border border-slate-200 opacity-60 bg-white transition flex items-center gap-3";
        }
      }
    });
  }

  if (slots) {
    if (slots.has_cultivable_land !== undefined) {
      summaryPrimary.textContent = slots.has_cultivable_land ? "Owns Land" : "No Land";
    } else if (slots.age !== undefined) {
      summaryPrimary.textContent = `${slots.age} Years`;
    }

    if (slots.annual_family_income !== undefined) {
      summarySecondary.textContent = `₹${slots.annual_family_income.toLocaleString('en-IN')}`;
    } else if (slots.is_bpl !== undefined) {
      summarySecondary.textContent = slots.is_bpl ? "BPL Certified" : "Non-BPL";
    }

    if (slots.is_govt_employee_or_pensioner !== undefined) {
      summaryExclusion.textContent = slots.is_govt_employee_or_pensioner ? "Govt Pension/Job" : "No Exclusion";
    } else if (slots.paid_income_tax !== undefined) {
      summaryExclusion.textContent = slots.paid_income_tax ? "Tax Payer" : "Non-Taxpayer";
    }
  }
}

function resetCaseSummary() {
  activeSchemePill.textContent = "Awaiting Scheme";
  activeSchemePill.className = "px-2.5 py-0.5 rounded-full text-[10px] font-bold bg-slate-100 text-slate-600";
  summaryScheme.textContent = "—";
  summaryPrimary.textContent = "—";
  summarySecondary.textContent = "—";
  summaryExclusion.textContent = "—";
  Object.values(schemeCards).forEach(card => {
    if (card) card.className = "scheme-card p-3 rounded-xl border border-slate-200 transition bg-white flex items-center gap-3";
  });
}

function showWarning(msg) {
  audioWarningText.textContent = msg;
  audioWarning.classList.remove("hidden");
}

function hideWarning() {
  audioWarning.classList.add("hidden");
}

// -------------------------------------------------------------
// 3. BARGE-IN & SPEAKING MANAGEMENT (B1, B3)
// -------------------------------------------------------------
function startAgentSpeaking(base64Audio) {
  setCallState("SPEAKING");
  speakingStartTime = Date.now();
  const currentGen = callGeneration;

  // Keep microphone stream open for barge-in detection during speaking
  setupMicrophoneStreamForBargeIn();

  player.play(base64Audio, () => {
    if (callGeneration !== currentGen) return;
    if (isCallMode) {
      startListening();
    } else {
      setCallState("IDLE");
    }
  }, currentGen);
}

// Replay button
replayBtn.addEventListener("click", () => {
  if (lastAgentAudioBase64) {
    startAgentSpeaking(lastAgentAudioBase64);
  }
});

// End Call Handler (B1)
endCallBtn.addEventListener("click", () => {
  endCall("USER_ENDED");
});

async function endCall(reason = "NORMAL") {
  callGeneration++; // Invalidate any in-flight turns
  isCallMode = false;
  clearInterval(callTimerInterval);
  clearTimeout(silenceTimer);

  // Stop Audio Player immediately (<200ms)
  player.stop();

  // Abort any in-flight server requests
  if (inFlightAbortController) {
    inFlightAbortController.abort();
    inFlightAbortController = null;
  }

  // Teardown microphone tracks and audio context
  teardownMicrophone();

  // Notify server to mark session ended & log abandoned if incomplete
  if (sessionId) {
    try {
      const fd = new FormData();
      fd.append("session_id", sessionId);
      fd.append("reason", reason);
      fetch("/api/session/end", { method: "POST", body: fd });
    } catch (e) {
      console.error("End session call failed:", e);
    }
  }

  // Update UI elements
  startCallBtn.classList.remove("hidden");
  endCallBtn.classList.add("hidden");
  endCallBtn.classList.remove("flex");
  callTimerBadge.classList.add("hidden");
  audioMeterBar.style.width = "0%";
  dbValue.textContent = "-∞ dB";

  setCallState("ENDED");
}

// Start Call Button (Unlocks browser AudioContext)
startCallBtn.addEventListener("click", async () => {
  isCallMode = true;
  callSeconds = 0;
  callGeneration++;
  startCallBtn.classList.add("hidden");
  endCallBtn.classList.remove("hidden");
  endCallBtn.classList.add("flex");
  callTimerBadge.classList.remove("hidden");
  callTimerBadge.classList.add("flex");

  // Call timer interval with 5-minute safety cap
  callTimerInterval = setInterval(() => {
    callSeconds++;
    const mins = String(Math.floor(callSeconds / 60)).padStart(2, '0');
    const secs = String(callSeconds % 60).padStart(2, '0');
    callTimer.textContent = `${mins}:${secs}`;

    if (callSeconds >= 300) {
      endCall("CALL_DURATION_EXCEEDED");
    }
  }, 1000);

  if (lastAgentAudioBase64) {
    startAgentSpeaking(lastAgentAudioBase64);
  } else {
    await initSession();
  }
});

// Push-to-Talk Button
recordBtn.addEventListener("click", async () => {
  if (callState === "SPEAKING") {
    // User tapped orb while speaking -> manual barge in!
    player.stop();
    startListening();
    return;
  }

  if (callState === "LISTENING") {
    stopListeningAndSend();
  } else {
    startListening();
  }
});

// -------------------------------------------------------------
// 4. MICROPHONE & BARGE-IN VAD LOGIC (B3)
// -------------------------------------------------------------
let consecutiveBargeInFrames = 0;
let consecutiveSilenceFrames = 0;
let speechDetectedInTurn = false;

async function setupMicrophoneStreamForBargeIn() {
  if (mediaStream && audioContext && audioContext.state !== "closed") {
    return; // Already streaming
  }

  try {
    mediaStream = await navigator.mediaDevices.getUserMedia({
      audio: {
        channelCount: 1,
        echoCancellation: true,
        noiseSuppression: true,
        autoGainControl: true
      }
    });

    audioContext = new (window.AudioContext || window.webkitAudioContext)();
    const source = audioContext.createMediaStreamSource(mediaStream);
    scriptProcessor = audioContext.createScriptProcessor(2048, 1, 1);

    scriptProcessor.onaudioprocess = (e) => {
      const inputData = e.inputBuffer.getChannelData(0);
      
      // Compute RMS for live level meter & VAD
      let sum = 0;
      for (let i = 0; i < inputData.length; i++) {
        const val = inputData[i];
        sum += val * val;
        if (callState === "LISTENING") {
          pcmSamples.push(val);
        } else {
          // Pre-roll buffer during SPEAKING (keep last 300ms ~ 4800 samples)
          preRollBuffer.push(val);
          if (preRollBuffer.length > 4800) preRollBuffer.shift();
        }
      }

      const rms = Math.sqrt(sum / inputData.length);
      const db = 20 * Math.log10(Math.max(rms, 1e-4));

      // Update meter
      const meterPercent = Math.min(100, Math.max(0, (db + 60) * 1.8));
      audioMeterBar.style.width = `${meterPercent}%`;
      dbValue.textContent = `${Math.round(db)} dB`;

      // -------------------------------------------------------
      // CASE A: BARGE-IN DETECTION DURING SPEAKING (Task B3)
      // -------------------------------------------------------
      if (callState === "SPEAKING") {
        const elapsedSinceSpeaking = Date.now() - speakingStartTime;
        // Ignore first 300ms grace window to prevent initial acoustic burst
        if (elapsedSinceSpeaking > 300) {
          // Elevated threshold during playback (-28 dB)
          if (db > -28) {
            consecutiveBargeInFrames++;
            // ~250-300ms of sustained speech (6 frames of 2048 samples at 44.1k)
            if (consecutiveBargeInFrames >= 6) {
              console.log("BARGE-IN TRIGGERED: User interrupted agent speech!");
              consecutiveBargeInFrames = 0;
              player.stop(); // Stop audio immediately (<200ms)
              startListening(true); // Transition to listening with pre-roll
            }
          } else {
            consecutiveBargeInFrames = Math.max(0, consecutiveBargeInFrames - 1);
          }
        }
      }

      // -------------------------------------------------------
      // CASE B: SILENCE DETECTION DURING LISTENING (Task T2)
      // -------------------------------------------------------
      if (callState === "LISTENING") {
        if (db > -35) {
          speechDetectedInTurn = true;
          consecutiveSilenceFrames = 0;
        } else if (speechDetectedInTurn) {
          consecutiveSilenceFrames++;
          // ~1.2s post-speech silence (25 frames)
          if (consecutiveSilenceFrames > 25 && isCallMode) {
            stopListeningAndSend();
          }
        }
      }
    };

    source.connect(scriptProcessor);
    scriptProcessor.connect(audioContext.destination);

  } catch (err) {
    console.error("Microphone setup failed:", err);
    showWarning("Microphone access denied. Please grant microphone permissions.");
  }
}

async function startListening(fromBargeIn = false) {
  setCallState("LISTENING");
  pcmSamples = [];
  speechDetectedInTurn = false;
  consecutiveSilenceFrames = 0;

  // If entering from barge-in, prepend pre-roll buffer so initial words are preserved
  if (fromBargeIn && preRollBuffer.length > 0) {
    pcmSamples = [...preRollBuffer];
    preRollBuffer = [];
    speechDetectedInTurn = true;
  }

  await setupMicrophoneStreamForBargeIn();

  // 8s Silence Timeout Prompt in Call Mode
  if (isCallMode) {
    clearTimeout(silenceTimer);
    silenceTimer = setTimeout(() => {
      if (callState === "LISTENING" && !speechDetectedInTurn) {
        stopListeningAndSend();
      }
    }, 8000);
  }
}

async function stopListeningAndSend() {
  if (callState !== "LISTENING") return;
  setCallState("THINKING");
  clearTimeout(silenceTimer);

  const origSampleRate = audioContext ? audioContext.sampleRate : 44100;
  const resampled = resample(pcmSamples, origSampleRate, 16000);
  const wavBlob = encodeWAV(resampled, 16000);

  currentTurnId++;
  await sendAudioTurn(wavBlob, currentTurnId);
}

function teardownMicrophone() {
  if (scriptProcessor) {
    scriptProcessor.disconnect();
    scriptProcessor = null;
  }
  if (mediaStream) {
    mediaStream.getTracks().forEach(t => t.stop());
    mediaStream = null;
  }
  if (audioContext && audioContext.state !== "closed") {
    audioContext.close();
    audioContext = null;
  }
}

// -------------------------------------------------------------
// 5. SERVER TURN COMMUNICATION (B1, B2)
// -------------------------------------------------------------
async function sendAudioTurn(audioBlob, turnId) {
  const currentGen = callGeneration;
  inFlightAbortController = new AbortController();

  const formData = new FormData();
  formData.append("session_id", sessionId);
  formData.append("language", currentLanguage);
  formData.append("turn_id", turnId);
  formData.append("audio_file", audioBlob, "recording.wav");

  let retryCount = 0;
  const maxRetries = 2;

  while (retryCount <= maxRetries) {
    try {
      const res = await fetch("/api/turn", {
        method: "POST",
        body: formData,
        signal: inFlightAbortController.signal
      });

      if (callGeneration !== currentGen || callState === "ENDED") {
        console.log("Discarding response for stale call generation / ended call");
        return;
      }

      if (!res.ok) {
        // Handle transient 409, 429, 500, 502, 504 without ending call
        if ((res.status >= 500 || res.status === 429 || res.status === 409) && retryCount < maxRetries) {
          retryCount++;
          console.warn(`Transient turn error HTTP ${res.status}. Retrying (${retryCount}/${maxRetries})...`);
          await new Promise(r => setTimeout(r, 400 * retryCount));
          continue;
        }
      }

      const data = await res.json();

      if (data.user_transcript) {
        appendUserBubble(data.user_transcript);
      }
      
      appendAgentBubble(data.agent_text, data.evaluation);

      if (data.scheme_id || data.evaluation) {
        updateCaseSummary(data.scheme_id, data.evaluation?.slots || {}, data.evaluation);
      }

      if (data.latencies) {
        latencyDetails.classList.remove("hidden");
        latVal.textContent = `${data.latencies.total}s (STT: ${data.latencies.stt}s, TTS: ${data.latencies.tts}s)`;
      }

      if (data.audio_base64) {
        lastAgentAudioBase64 = data.audio_base64;
        startAgentSpeaking(data.audio_base64);
      } else {
        setCallState(isCallMode ? "LISTENING" : "IDLE");
      }

      if (data.completed) {
        // In Phase 4, the call does NOT end automatically after verdict.
        // The agent asks follow-up questions (how to apply, documents, helpline).
        console.log("Verdict reached; session continues in FOLLOWUP mode.");
      }
      return; // Turn finished successfully

    } catch (err) {
      if (err.name === "AbortError") {
        console.log("In-flight turn fetch aborted on End Call");
        return;
      }
      if (retryCount < maxRetries) {
        retryCount++;
        console.warn(`Turn network failure, retrying (${retryCount}/${maxRetries})...`, err);
        await new Promise(r => setTimeout(r, 400 * retryCount));
        continue;
      }
      console.error("Turn failed after retries:", err);
      showWarning("Connection glitch. Please speak again.");
      setCallState(isCallMode ? "LISTENING" : "IDLE");
      return;
    } finally {
      inFlightAbortController = null;
    }
  }
}

// Resampling & WAV Helpers
function encodeWAV(samples, sampleRate) {
  const buffer = new ArrayBuffer(44 + samples.length * 2);
  const view = new DataView(buffer);

  function writeString(view, offset, string) {
    for (let i = 0; i < string.length; i++) {
      view.setUint8(offset + i, string.charCodeAt(i));
    }
  }

  writeString(view, 0, 'RIFF');
  view.setUint32(4, 36 + samples.length * 2, true);
  writeString(view, 8, 'WAVE');
  writeString(view, 12, 'fmt ');
  view.setUint32(16, 16, true);
  view.setUint16(20, 1, true);
  view.setUint16(22, 1, true);
  view.setUint32(24, sampleRate, true);
  view.setUint32(28, sampleRate * 2, true);
  view.setUint16(32, 2, true);
  view.setUint16(34, 16, true);
  writeString(view, 36, 'data');
  view.setUint32(40, samples.length * 2, true);

  let offset = 44;
  for (let i = 0; i < samples.length; i++, offset += 2) {
    let s = Math.max(-1, Math.min(1, samples[i]));
    view.setInt16(offset, s < 0 ? s * 0x8000 : s * 0x7FFF, true);
  }

  return new Blob([view], { type: 'audio/wav' });
}

function resample(samples, fromRate, toRate) {
  if (fromRate === toRate) return samples;
  const ratio = fromRate / toRate;
  const newLength = Math.round(samples.length / ratio);
  const result = new Float32Array(newLength);
  for (let i = 0; i < newLength; i++) {
    const origIndex = i * ratio;
    const i1 = Math.floor(origIndex);
    const i2 = Math.min(i1 + 1, samples.length - 1);
    const frac = origIndex - i1;
    result[i] = samples[i1] * (1 - frac) + samples[i2] * frac;
  }
  return result;
}

// -------------------------------------------------------------
// 6. SIMULATE / DEMO WALKTHROUGH MODE (B4)
// -------------------------------------------------------------
async function simulateTurn(text) {
  appendUserBubble(text);
  setCallState("THINKING");

  try {
    const res = await fetch(`/api/demo/turn?text=${encodeURIComponent(text)}&session_id=${sessionId}&language=${currentLanguage}`, { method: "POST" });
    const data = await res.json();
    appendAgentBubble(data.agent_text, data.evaluation);
    if (data.scheme_id || data.evaluation) {
      updateCaseSummary(data.scheme_id, data.evaluation?.slots || {}, data.evaluation);
    }
    if (data.audio_base64) {
      lastAgentAudioBase64 = data.audio_base64;
      startAgentSpeaking(data.audio_base64);
    } else {
      setCallState("IDLE");
    }
  } catch (e) {
    console.error("Simulate turn failed:", e);
    setCallState("IDLE");
  }
}

demoModeBtn.addEventListener("click", async () => {
  const demoScenarios = {
    "hi-IN": ["मुझे पीएम किसान योजना जाँचना है", "हाँ मेरे पास अपनी खेती की ज़मीन है", "नहीं यह निजी है", "नहीं कोई सरकारी नौकरी नहीं है", "नहीं इनकम टैक्स नहीं भरते"],
    "en-IN": ["Check old age pension scheme", "I am 65 years old", "Yes we are in BPL category", "No I receive no other pension"],
    "ta-IN": ["PM Kisan scheme", "Yes", "No", "No", "No"]
  };

  const steps = demoScenarios[currentLanguage] || demoScenarios["en-IN"];
  for (const stepText of steps) {
    if (callState === "ENDED") break;
    await simulateTurn(stepText);
    await new Promise(resolve => setTimeout(resolve, 3500));
  }
});
